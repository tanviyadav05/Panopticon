# API documentation

Every HTTP endpoint that crosses a laptop boundary, in one place. (Internal
calls within one laptop's process — e.g. `blue_controller.py` calling
`pod_isolator.py` directly — aren't HTTP and aren't listed here.)

## Referee ingest — `POST http://command-laptop:9600/ingest`

Owned by `referee/env/action_executor.py`. Called by
`observer/pipeline/publisher.py` once per aggregation window.

```json
// request
{ "timestamp": 1234567890.1, "field_names": ["network.total_connections", ...], "state": [0.12, ...] }
// response
{ "received": true }
```

## Red attacker — `red-laptop:8081`

Owned by `red-team/attacks/red_attacker.py`.

- `POST /act` `{"action": "<name from common/action_spaces.RED_ACTIONS>"}` →
  `{"ok": true, "action": "...", "synthetic_effect": {"<pressure>": <magnitude>}, "timestamp": ...}`
- `POST /decide` `{"observation": [7 floats]}` → `{"action": "<name>"}`
- `GET /health` → `{"status": "ok", "role": "red-attacker"}`
- `GET /metrics` → Prometheus exposition format

## Blue controller — `blue-laptop:8082`

Owned by `blue-team/countermeasures/blue_controller.py`.

- `POST /act` `{"action": "<name from common/action_spaces.BLUE_ACTIONS>"}` →
  shape depends on the action; always includes `{"ok": bool, "action": "..."}`,
  plus action-specific fields (e.g. `isolate_pod` includes `policy_name`).
- `POST /decide` `{"observation": [14 floats]}` → `{"action": "<name>"}`
- `GET /health` → `{"status": "ok", "role": "blue-controller", "cluster_available": bool}`
- `GET /metrics` → Prometheus exposition format

## LLM gateway — `llm-laptop:8090`

Owned by `llm-core/server/llm_server.py`. See `docs/multi_agent_llm.md`
for the full picture; summary here.

Legacy, unchanged — called via `llm-core/server/api_gateway.py`'s
`LLMGateway` class (which also logs every call into `llm-core/memory/`)
rather than directly, where possible:

- `POST /generate` `{"prompt": str, "max_tokens": int, "temperature": float}` →
  `{"text": str, "backend": "mock"|"ollama"|"transformers", "latency_s": float}`
- `GET /health` → `{"status": "ok", "backend": "..."}`

New — the multi-agent stack (Planner/Researcher/Coder/Critic):

- `POST /agent/run` `{"task": str, "target_context": dict?, "max_iterations": int?}` →
  the full final graph state: `plan`, `final_answer`, `status`, `total_steps`,
  `iteration`, `history` (per-turn agent/model/latency/mocked), `elapsed_s`, `task_id`
- `GET /agents` → configured roles/models + live tool/memory backend status
- `GET /memory/search?q=...&top_k=5` → reranked ChromaDB query results
- `GET /tasks/recent?limit=20` → recent task summaries from the SQLite metadata store
- `GET /metrics` → Prometheus exposition format (see `docs/observability.md`)

## Monitoring — `command-laptop:8000`

Owned by `monitoring/dashboard_server.py`.

- `GET /` — the dashboard itself (static files from `frontend/`)
- `POST /telemetry` — ingest one `TelemetryEvent` (see
  `monitoring/telemetry_api.py` for the full field list)
- `GET /telemetry/recent?limit=N` — last N events as JSON
- `GET /widgets/cpu` / `/widgets/network` / `/widgets/attack_timeline` —
  chart-ready shapes (see `monitoring/widgets/`)
- `GET /targets` / `GET /targets/active` / `POST /targets/select` —
  the target-picker registry (see `docs/multi_device_targets.md`)
- `GET /metrics` → Prometheus exposition format
- `WS /ws/live` — sends `{"type": "backlog", "events": [...]}` once on
  connect, then `{"type": "update", "events": [...]}` roughly every 300ms,
  plus `{"type": "targets_update", "targets": [...]}` roughly every 3s

## Automated-agent and control-console additions

- `POST red-laptop:8081/autonomy/tick` receives seven Red-visible telemetry
  values, chooses a local policy action, and returns only a simulated effect.
- `POST blue-laptop:8082/advise` receives 14 Blue telemetry values and
  returns a bounded local-LLM recommendation without applying it.
- `POST blue-laptop:8082/autonomy/tick` is dry-run by default. Its
  `apply: true` option is rejected unless `BLUE_AUTONOMY_APPLY=1` is set on
  the Blue laptop.
- `GET command-laptop:8000/control/status` reports Red, Blue, LLM, and
  simulated-Referee health. State-changing `/control/*` routes accept an
  optional `X-Panopticon-Token` when `PANOPTICON_CONTROL_TOKEN` is set.
- `POST /control/referee/reset`, `/control/referee/step`, and
  `/control/referee/policy-step` run locally in simulation. A policy step
  calls only remote `/decide` routes, never remote `/act` routes.
- `POST /control/referee/local-llm-analysis` submits a defensive-only,
  simulated-state review to the local LLM laptop.
- Dashboard Blue `isolate_pod` and `honeypot_redirect` require both
  `confirm_live: true` and `PANOPTICON_BLUE_LIVE_ARMED=1` on Laptop 05.

## The two non-HTTP contracts

Not HTTP, but just as cross-cutting, and worth listing here rather than
making someone find them by reading every file:

- **State schema** — `observer/pipeline/state_schema.json`, read by
  `observer/pipeline/state_encoder.py` and (via a relative import)
  `referee/env/observation_builder.py`. Defines the 14-field telemetry
  vector's field order and normalization ranges.
- **Action spaces** — `common/action_spaces.py`. Defines what action
  index N means for Red (6 actions) and Blue (5 actions); imported by
  `panopticon_env.py`, `attack_policy.py`, and `blue_controller.py`.
