"""Builds the Planner -> {Researcher | Coder} -> Critic -> Planner graph
and exposes run_agent_graph() as the one function callers need.

Each node function returns state["next"] naming where to go; a single
router function reads that field for every conditional edge, which keeps
the routing logic in one place (the nodes themselves) instead of smeared
across per-node edge-condition lambdas.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

from langgraph.graph import StateGraph, END

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> llm-core/
from config import load_config
from agents.base_agent import OllamaAgent
from agents.planner import make_planner_node
from agents.researcher import make_researcher_node
from agents.coder import make_coder_node
from agents.critic import make_critic_node
from graph.state import AgentState

logger = logging.getLogger("llm_core.agent_graph")

_compiled_graph = None
_agents_by_name: dict = {}


def _build_agent(name: str, cfg: dict) -> OllamaAgent:
    agent_cfg = cfg["agents"][name]
    with open(agent_cfg["system_prompt_path"]) as fh:
        system_prompt = fh.read()
    return OllamaAgent(
        name=name,
        model=agent_cfg["model"],
        system_prompt=system_prompt,
        host=cfg["ollama"]["host"],
        temperature=agent_cfg.get("temperature", 0.5),
        request_timeout_s=cfg["ollama"].get("request_timeout_s", 90.0),
        connect_timeout_s=cfg["ollama"].get("connect_timeout_s", 3.0),
    )


def _route(state: AgentState) -> str:
    nxt = state.get("next", "END")
    return "END" if nxt == "END" else nxt


def build_graph(config: Optional[dict] = None, web_browser=None, code_sandbox=None):
    """Builds (and caches) the compiled graph. Passing web_browser/
    code_sandbox lets the server wire in real tool instances; omit either
    to run with that tool disabled (nodes handle a None tool gracefully)."""
    global _compiled_graph, _agents_by_name
    if _compiled_graph is not None:
        return _compiled_graph

    cfg = config or load_config()

    for name in ("planner", "researcher", "coder", "critic"):
        _agents_by_name[name] = _build_agent(name, cfg)

    graph = StateGraph(AgentState)
    graph.add_node("planner", make_planner_node(_agents_by_name["planner"], max_plan_steps=cfg["graph"].get("max_plan_steps", 6)))
    graph.add_node("researcher", make_researcher_node(
        _agents_by_name["researcher"], web_browser=web_browser,
        max_results=cfg["tools"]["web_browser"].get("max_results", 5),
    ))
    graph.add_node("coder", make_coder_node(_agents_by_name["coder"], code_sandbox=code_sandbox))
    graph.add_node("critic", make_critic_node(_agents_by_name["critic"]))

    graph.set_entry_point("planner")
    graph.add_conditional_edges("planner", _route, {"researcher": "researcher", "coder": "coder", "END": END})
    graph.add_conditional_edges("researcher", _route, {"critic": "critic", "END": END})
    graph.add_conditional_edges("coder", _route, {"critic": "critic", "END": END})
    graph.add_conditional_edges("critic", _route, {"planner": "planner", "researcher": "researcher", "coder": "coder", "END": END})

    _compiled_graph = graph.compile()
    return _compiled_graph


def run_agent_graph(
    task: str,
    target_context: Optional[dict] = None,
    max_iterations: Optional[int] = None,
    config: Optional[dict] = None,
    web_browser=None,
    code_sandbox=None,
    recursion_limit: int = 50,
) -> dict:
    """The one entry point callers need. Returns the final AgentState as a
    plain dict (plan, final_answer, status, full history, timing)."""
    cfg = config or load_config()
    graph = build_graph(cfg, web_browser=web_browser, code_sandbox=code_sandbox)

    initial_state: AgentState = {
        "task": task,
        "target_context": target_context or {},
        "plan": [],
        "next_step_type": "",
        "step_instruction": "",
        "research_findings": "",
        "research_confidence": 0.0,
        "code": "",
        "code_output": "",
        "code_executed": False,
        "critic_approved": False,
        "critic_feedback": "",
        "iteration": 0,
        "max_iterations": max_iterations or cfg["graph"].get("max_iterations", 4),
        "total_steps": 0,
        "max_total_steps": cfg["graph"].get("max_total_steps", 12),
        "status": "planning",
        "next": "",
        "history": [],
        "final_answer": "",
    }

    start = time.monotonic()
    final_state = graph.invoke(initial_state, config={"recursion_limit": recursion_limit})
    elapsed = time.monotonic() - start

    final_state = dict(final_state)
    final_state["elapsed_s"] = round(elapsed, 3)
    return final_state
