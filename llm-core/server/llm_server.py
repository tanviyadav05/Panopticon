"""The long-running service: loads the InferenceEngine (legacy single-shot
backend) AND the 4-agent LangGraph stack once at startup, and serves both
over HTTP. Run this on the LLM laptop (01):

    python3 llm_server.py                              # LLM_BACKEND=mock, Ollama unreachable -> agents mock-fallback too
    LLM_BACKEND=ollama python3 llm_server.py            # legacy /generate uses real Ollama
    OLLAMA_HOST=http://localhost:11434 python3 llm_server.py   # overrides agents_config.yaml's ollama.host

Two API surfaces, both live on this one process:

  LEGACY (unchanged) — red-team/generators/llm_payload_generator.py and
  any blue-team equivalent already point LLM_GATEWAY_URL at /generate.
  That endpoint and its behavior are untouched by this change.
    POST /generate    {"prompt", "max_tokens", "temperature"} -> {"text", "backend", "latency_s"}
    GET  /health

  NEW — the multi-agent stack from LLM_RESEARCH.txt (Planner/Researcher/
  Coder/Critic), for tasks that need actual reasoning/iteration rather
  than a single completion.
    POST /agent/run   {"task", "target_context"?, "max_iterations"?} -> full final AgentState
    GET  /agents       -> configured roles, models, tool availability
    GET  /memory/search?q=...&top_k=5  -> vector memory query (reranked)
    GET  /metrics       -> Prometheus exposition format, scraped by observability/prometheus/prometheus.yml
"""
from __future__ import annotations

import os
import sys
import time

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))               # -> llm-core/server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> llm-core/
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common")))

from inference_engine import InferenceEngine
from config import load_config
from graph.agent_graph import run_agent_graph
from tools.web_browser import WebBrowser
from tools.code_sandbox import CodeSandbox
from memory.vector_store import VectorMemory
from memory.embeddings import EmbeddingModel
from memory.reranker import Reranker
from memory.metadata_store import MetadataStore
from metrics import mount_metrics, counter, histogram


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 128
    temperature: float = 0.7


class AgentRunRequest(BaseModel):
    task: str
    target_context: dict = {}
    max_iterations: int | None = None


# --- Prometheus metrics (module-level: one process, one registration) -----
LEGACY_REQUESTS = counter("llm_core_generate_requests_total", "Legacy /generate calls", ("backend",))
LEGACY_LATENCY = histogram("llm_core_generate_latency_seconds", "Legacy /generate latency")
AGENT_RUNS = counter("llm_core_agent_runs_total", "Full agent-graph runs", ("status",))
AGENT_RUN_LATENCY = histogram("llm_core_agent_run_latency_seconds", "Full agent-graph run latency")
AGENT_TURNS = counter("llm_core_agent_turns_total", "Individual agent turns within a run", ("agent", "mocked"))


def build_app() -> FastAPI:
    engine = InferenceEngine()
    cfg = load_config()

    embedder = EmbeddingModel(cfg["memory"]["embedding_model"])
    reranker = Reranker(cfg["memory"]["reranker_model"])
    vector_memory = VectorMemory(cfg["memory"]["chroma_persist_dir_abs"], embedding_model=embedder)
    metadata_store = MetadataStore(cfg["memory"]["sqlite_path_abs"])
    web_browser = WebBrowser(headless=cfg["tools"]["web_browser"]["headless"], timeout_s=cfg["tools"]["web_browser"]["timeout_s"])
    code_sandbox = CodeSandbox(
        image=cfg["tools"]["code_sandbox"]["image"],
        timeout_s=cfg["tools"]["code_sandbox"]["timeout_s"],
        mem_limit=cfg["tools"]["code_sandbox"]["mem_limit"],
        network_disabled=cfg["tools"]["code_sandbox"]["network_disabled"],
    )

    app = FastAPI(title="Panopticon LLM Core")

    # --- legacy single-shot endpoint (unchanged behavior) ------------------
    @app.post("/generate")
    def generate(req: GenerateRequest):
        start = time.time()
        text = engine.generate(req.prompt, req.max_tokens, req.temperature)
        latency = time.time() - start
        LEGACY_REQUESTS.labels(backend=engine.backend_name).inc()
        LEGACY_LATENCY.observe(latency)
        return {"text": text, "backend": engine.backend_name, "latency_s": round(latency, 4)}

    @app.get("/health")
    def health():
        return {"status": "ok", "backend": engine.backend_name}

    # --- multi-agent stack ---------------------------------------------------
    @app.post("/agent/run")
    def agent_run(req: AgentRunRequest):
        task_id = metadata_store.record_task_start(req.task, req.target_context)
        result = run_agent_graph(
            task=req.task, target_context=req.target_context,
            max_iterations=req.max_iterations, config=cfg,
            web_browser=web_browser, code_sandbox=code_sandbox,
        )
        for turn in result["history"]:
            metadata_store.record_turn(task_id, turn["agent"], turn["model"], "", turn["text"], turn["latency_s"], turn["mocked"])
            AGENT_TURNS.labels(agent=turn["agent"], mocked=str(turn["mocked"])).inc()
        metadata_store.record_task_end(task_id, result["status"], result["final_answer"], result["total_steps"])

        vector_memory.add(
            f"Task: {req.task}\nAnswer: {result['final_answer']}",
            metadata={"task_id": task_id, "status": result["status"], **({"device_type": req.target_context.get("device_type")} if req.target_context.get("device_type") else {})},
        )

        AGENT_RUNS.labels(status=result["status"]).inc()
        AGENT_RUN_LATENCY.observe(result["elapsed_s"])
        result["task_id"] = task_id
        return result

    @app.get("/agents")
    def list_agents():
        return {
            name: {"model": a["model"], "role": a["role"], "description": a.get("description", "")}
            for name, a in cfg["agents"].items()
        } | {
            "_tools": {
                "web_browser_available": web_browser.available,
                "code_sandbox_available": code_sandbox.available,
            },
            "_memory": {
                "embedding_backend": embedder.backend,
                "reranker_backend": reranker.backend,
                "vector_memory_count": vector_memory.count(),
            },
        }

    @app.get("/memory/search")
    def memory_search(q: str, top_k: int = 5):
        retrieved = vector_memory.query(q, top_k=cfg["memory"]["top_k_retrieval"])
        if not retrieved:
            return {"query": q, "results": []}
        ranked = reranker.rerank(q, [r["text"] for r in retrieved], top_k=min(top_k, cfg["memory"]["top_k_after_rerank"]))
        return {"query": q, "results": [{**retrieved[idx], "rerank_score": score} for idx, score in ranked]}

    @app.get("/tasks/recent")
    def recent_tasks(limit: int = 20):
        return metadata_store.recent_tasks(limit)

    mount_metrics(app)
    return app


if __name__ == "__main__":
    app = build_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8090")))
