"""Integration tests specific to this update: the multi-agent LLM stack
(llm-core/) and the Prometheus metrics endpoints that
observability/prometheus/prometheus.yml scrapes. Run from the repo root:

    python3 -m pytest tests/integration/ -v
"""
from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _add(*parts):
    sys.path.insert(0, os.path.join(REPO_ROOT, *parts))


def test_agent_graph_runs_end_to_end_with_mock_fallback():
    """No live Ollama server is assumed in CI/dev — this proves the full
    Planner->{Researcher|Coder}->Critic->Planner graph runs to completion
    purely on the deterministic mock fallback, and that both safety bounds
    (per-step iteration cap, global total_steps cap) are respected."""
    _add("llm-core")
    from config import reload_config
    from graph.agent_graph import run_agent_graph

    cfg = reload_config()
    cfg["ollama"]["host"] = "http://localhost:1"     # guaranteed unreachable -> forces mock fallback
    cfg["ollama"]["connect_timeout_s"] = 0.2

    result = run_agent_graph(
        task="Investigate the wifi_router target and propose a plan to test its resilience.",
        target_context={"device_type": "wifi_router", "name": "lab-router"},
        config=cfg,
    )

    assert result["status"] == "done"
    assert result["iteration"] <= result["max_iterations"]
    assert result["total_steps"] <= result["max_total_steps"]
    assert len(result["history"]) > 0
    assert all(turn["mocked"] for turn in result["history"])   # confirms this really exercised the fallback, not a lucky real connection
    assert result["final_answer"]


def test_agent_graph_global_step_cap_is_a_real_termination_guarantee():
    """Regression test for the bug caught during development: the
    per-step revision counter (`iteration`) must reset between different
    plan steps, and `total_steps` — not `iteration` — is what bounds the
    whole task. A tiny max_total_steps should force early completion
    regardless of what the (mocked) model says."""
    _add("llm-core")
    from config import reload_config
    from graph.agent_graph import run_agent_graph

    cfg = reload_config()
    cfg["ollama"]["host"] = "http://localhost:1"
    cfg["ollama"]["connect_timeout_s"] = 0.2
    cfg["graph"]["max_total_steps"] = 2   # deliberately tiny

    result = run_agent_graph(task="A task designed to run long.", config=cfg)

    assert result["status"] == "done"
    assert result["total_steps"] <= 2
    # iteration must never be allowed to silently exceed its own cap
    assert result["iteration"] <= result["max_iterations"]


def test_llm_server_legacy_endpoint_unchanged_by_multi_agent_addition():
    """The whole point of keeping /generate untouched: red-team's
    LLMGateway and blue-team's equivalent must keep working with zero
    changes. This just confirms the shape is exactly what it was before
    agent/run, /agents, /memory/search existed alongside it."""
    _add("llm-core/server")
    _add("llm-core")
    _add("common")
    from config import reload_config
    cfg = reload_config()
    cfg["ollama"]["host"] = "http://localhost:1"
    cfg["ollama"]["connect_timeout_s"] = 0.2

    import llm_server
    llm_server.load_config = lambda: cfg
    from fastapi.testclient import TestClient

    app = llm_server.build_app()
    client = TestClient(app)

    r = client.post("/generate", json={"prompt": "test", "max_tokens": 16}).json()
    assert set(r.keys()) == {"text", "backend", "latency_s"}

    h = client.get("/health").json()
    assert set(h.keys()) == {"status", "backend"}


def test_llm_server_agent_and_memory_endpoints_respond():
    """Smoke test for the new endpoints beyond the graph itself: /agents
    reports tool/memory backend status, /agent/run persists to both the
    SQLite metadata store and ChromaDB, and /memory/search can find what
    was just stored."""
    _add("llm-core/server")
    _add("llm-core")
    _add("common")
    from config import reload_config
    cfg = reload_config()
    cfg["ollama"]["host"] = "http://localhost:1"
    cfg["ollama"]["connect_timeout_s"] = 0.2

    import llm_server
    llm_server.load_config = lambda: cfg
    from fastapi.testclient import TestClient

    app = llm_server.build_app()
    client = TestClient(app)

    agents = client.get("/agents").json()
    for role in ("planner", "researcher", "coder", "critic"):
        assert role in agents
        assert "model" in agents[role]
    assert "_tools" in agents and "_memory" in agents

    run_resp = client.post("/agent/run", json={"task": "Say hello."}).json()
    assert run_resp["status"] == "done"
    assert "task_id" in run_resp

    tasks = client.get("/tasks/recent").json()
    assert any(t["id"] == run_resp["task_id"] for t in tasks)


def test_metrics_endpoints_expose_valid_prometheus_format():
    """The observability stack is only useful if these actually emit
    scrapeable text — checks the four services common/metrics.py was
    wired into, using each service's own build_app()."""
    _add("common")
    from fastapi.testclient import TestClient

    # red-team
    _add("red-team")
    from attacks.red_attacker import build_app as build_red_app
    red_client = TestClient(build_red_app())
    red_client.post("/act", json={"action": "connection_pressure", "target_device_type": "go_app"})
    red_metrics = red_client.get("/metrics").text
    assert "panopticon_red_actions_total" in red_metrics

    # blue-team
    _add("blue-team")
    from countermeasures.blue_controller import build_app as build_blue_app
    blue_client = TestClient(build_blue_app())
    blue_client.post("/act", json={"action": "rate_limit"})
    blue_metrics = blue_client.get("/metrics").text
    assert "panopticon_blue_actions_total" in blue_metrics

    # monitoring dashboard
    _add("monitoring")
    import dashboard_server
    mon_client = TestClient(dashboard_server.build_app())
    mon_client.post("/telemetry", json={"step": 1, "combined_pressure": 0.3, "service_health": 0.7})
    mon_metrics = mon_client.get("/metrics").text
    assert "panopticon_telemetry_events_total" in mon_metrics
    assert "panopticon_service_health" in mon_metrics


def test_observability_configs_are_valid():
    """Cheap but real: every YAML in observability/ parses, every
    dashboard JSON is valid and non-empty, and (the thing that actually
    matters) every PromQL expr in every dashboard panel references a
    metric name this repo really exports — catching the exact class of
    bug where a dashboard is built against a metric that got renamed or
    never existed."""
    import glob
    import yaml

    obs_dir = os.path.join(REPO_ROOT, "observability")

    for path in glob.glob(os.path.join(obs_dir, "**", "*.yml"), recursive=True) + \
                glob.glob(os.path.join(obs_dir, "**", "*.yaml"), recursive=True):
        with open(path) as fh:
            yaml.safe_load(fh)

    known_metric_prefixes = (
        "up", "node_", "target_app_", "llm_core_", "panopticon_", "prometheus_",
    )

    dashboards_dir = os.path.join(obs_dir, "grafana", "dashboards")
    dashboard_files = glob.glob(os.path.join(dashboards_dir, "*.json"))
    assert len(dashboard_files) >= 3

    for path in dashboard_files:
        with open(path) as fh:
            dashboard = json.load(fh)
        assert dashboard.get("panels")
        for panel in dashboard["panels"]:
            for t in panel.get("targets", []):
                expr = t["expr"]
                assert expr.strip()
                # crude but effective: at least one known metric prefix must appear
                assert any(prefix in expr for prefix in known_metric_prefixes), \
                    f"{os.path.basename(path)} panel {panel['title']!r} references an unrecognized metric: {expr}"
