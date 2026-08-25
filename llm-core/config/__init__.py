"""Loads llm-core/config/agents_config.yaml once and hands back a plain
dict, with the two path fields (system_prompt_file, memory paths) resolved
to absolute paths so callers don't need to know where the config file
lives relative to them.
"""
from __future__ import annotations

import os
import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "agents_config.yaml")
_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")

_cached_config: dict | None = None


def load_config(path: str = _CONFIG_PATH) -> dict:
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    with open(path) as fh:
        cfg = yaml.safe_load(fh)

    # OLLAMA_HOST env var overrides agents_config.yaml's ollama.host, so a
    # laptop-specific override doesn't require editing the checked-in
    # config file — see server/llm_server.py's module docstring, which
    # documents this.
    env_ollama_host = os.environ.get("OLLAMA_HOST")
    if env_ollama_host:
        cfg.setdefault("ollama", {})["host"] = env_ollama_host

    # tracing.langsmith_enabled in the YAML is the single source of truth
    # for whether tracing is on — it works by setting the env vars
    # LangGraph/LangSmith's own ambient instrumentation actually reads
    # (LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT), rather than requiring
    # every caller to set those directly. An explicit env var already set
    # by the caller wins over the config file either way. Without
    # LANGCHAIN_API_KEY set (a secret, deliberately not something this
    # config file controls), tracing has nowhere to send to and silently
    # no-ops — see agents_config.yaml's own comment on this.
    tracing_cfg = cfg.get("tracing", {})
    if tracing_cfg.get("langsmith_enabled"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", tracing_cfg.get("project_name", "project-panopticon"))
        if not os.environ.get("LANGCHAIN_API_KEY"):
            import logging
            logging.getLogger("llm_core.config").warning(
                "tracing.langsmith_enabled is true but LANGCHAIN_API_KEY is not set — "
                "tracing will no-op rather than send anywhere"
            )

    for agent_name, agent_cfg in cfg.get("agents", {}).items():
        rel = agent_cfg.get("system_prompt_file", "")
        agent_cfg["system_prompt_path"] = os.path.join(_PROMPTS_DIR, rel)

    llm_core_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mem = cfg.get("memory", {})
    mem["chroma_persist_dir_abs"] = os.path.normpath(os.path.join(llm_core_root, "server", mem.get("chroma_persist_dir", "../data/chroma")))
    mem["sqlite_path_abs"] = os.path.normpath(os.path.join(llm_core_root, "server", mem.get("sqlite_path", "../data/panopticon_memory.db")))

    _cached_config = cfg
    return cfg


def reload_config(path: str = _CONFIG_PATH) -> dict:
    """Bypasses the cache — mainly useful for tests that swap configs."""
    global _cached_config
    _cached_config = None
    return load_config(path)
