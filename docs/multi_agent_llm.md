# Multi-agent LLM stack

`llm-core/` implements the architecture from the team's `LLM_RESEARCH.txt`:
four specialized agents, each a different model, coordinated by a
LangGraph state machine, backed by real vector + structured memory and
two real tools (a Docker code sandbox, a Playwright web browser).

## The four agents

| Role | Model (real deployment) | Job |
|---|---|---|
| Planner/Manager | Hermes 3 8B | Breaks a task into steps, decides Research vs. Code vs. Done after each step |
| Researcher | Dolphin-Llama3 8B | Gathers information for the current step, optionally via the web_browser tool |
| Coder/Executor | Qwen3 Q4_K_M (`qwen3:8b-q4_K_M` default) | Writes code for the current step, optionally executes it via the code_sandbox tool |
| Critic/Reviewer | Qwen3 Q4_K_M (`qwen3:8b-q4_K_M` default) | Approves or rejects the Researcher/Coder's output; rejections get one more attempt |

All four run under **one Ollama daemon** on the LLM laptop (01) —
`llm-core/config/agents_config.yaml`'s `ollama.host` points every agent at
the same server; Ollama loads/unloads models on demand rather than
needing four separate processes. Model tags in that config are set to
sensible defaults (`hermes3:8b`, `dolphin-llama3:8b`, `qwen3:8b-q4_K_M`)
— check `ollama list` on your actual machine and adjust if your pulled
tags differ, especially for the Qwen3 Q4_K_M quant, which may have been
imported via a custom Modelfile rather than pulled from the official
library.

The research note names Qwen3 7B Q4_K_M. The default install uses the
current Ollama library's `qwen3:8b-q4_K_M` tag so the command works out of
the box; if you import an exact 7B Q4_K_M GGUF, set the Coder and Critic
model tags to that local name.

## The graph

```
        ┌──────────┐
   ┌───▶│ Planner  │◀────────────┐
   │    └────┬─────┘             │
   │         │ next_step_type    │ approved
   │    ┌────┴────┐              │
   │    ▼         ▼              │
   │ Researcher  Coder            │
   │    │         │               │
   │    └────┬────┘               │
   │         ▼                    │
   │      Critic ──────────────────┘
   │         │  rejected, iterations remain
   └─────────┘  (back to the SAME node for one more attempt)

   Planner also exits directly to END when next_step_type == "done"
   OR when total_steps hits max_total_steps (the real termination
   guarantee — see below).
```

Two separate, deliberately-not-conflated safety bounds
(`llm-core/graph/state.py`):

- **`iteration` / `max_iterations`** (default 4) — how many revision
  attempts a *single step* gets. Reset to 0 by the Planner every time it
  dispatches a genuinely new step; incremented by the Critic on rejection.
- **`total_steps` / `max_total_steps`** (default 12) — how many steps the
  Planner is allowed to dispatch across the *whole task*, ever, checked
  before trusting the model's own "done" judgment. This is what actually
  guarantees the graph terminates even if a model (or its mock stand-in)
  never says "done" — `max_iterations` alone only bounds revision loops on
  one step, not the total task length.

## Running without a live Ollama server

Every agent call that can't reach Ollama (wrong host, model not pulled,
daemon down — or simply no Ollama server at all, e.g. local dev) falls
back to a **deterministic mock response** shaped correctly for that
agent's role (`llm-core/agents/base_agent.py`). This means the entire
graph — routing, iteration caps, memory writes — is fully exercisable and
testable with zero infrastructure. Real output *quality* obviously
depends on the real models being loaded; the orchestration logic doesn't.

## Memory

Two complementary stores, both real and running locally (no server
process to babysit for either):

- **Vector memory** (`memory/vector_store.py`) — ChromaDB's embedded
  persistent client. Every completed `/agent/run` task gets written here;
  `/memory/search` retrieves + reranks against it.
- **Metadata store** (`memory/metadata_store.py`) — SQLAlchemy ORM over
  SQLite: one row per task, one row per agent turn (model, latency,
  whether it was mocked). `/tasks/recent` reads from here.

**Embeddings and reranking** try the real `BAAI/bge-small-en-v1.5` /
`BAAI/bge-reranker-base` models first, and fall back to a deterministic
hash-based / lexical-overlap scorer if the models can't be downloaded (no
internet access to huggingface.co, or just not cached yet). The fallback
keeps the whole retrieval pipeline testable end-to-end; it is not a
substitute for real semantic search. Pre-download the real models once,
with internet access:

```bash
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
python3 -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"
```

## Tools

- **`tools/code_sandbox.py`** — real Docker containers (no network, memory
  cap, wall-clock timeout) for whatever the Coder agent writes. Requires a
  running Docker daemon; **fails closed** with a clear error if one isn't
  available, rather than falling back to running untrusted
  model-generated code as a bare subprocess on the host. A subprocess
  isn't a sandbox, and code_sandbox won't pretend otherwise. Default
  image is `llm-core/docker/sandbox.Dockerfile` (Python + numpy/pandas/
  requests/matplotlib pre-installed, since the sandbox has no network
  access at runtime to `pip install` anything itself) — build it once
  with `docker build -t panopticon/code-sandbox:latest -f
  docker/sandbox.Dockerfile llm-core/`.
- **`tools/web_browser.py`** — real Playwright browser automation for the
  Researcher agent. Requires `playwright install chromium` to have been
  run once (downloads real browser binaries, needs internet access).
  Every method degrades to an empty result on any failure (browser
  unavailable, navigation timeout, changed page layout) rather than
  raising — a flaky page load shouldn't crash the whole graph.

## API surface

Both old and new live on `llm_server.py` (port 8090):

- `POST /generate` — **unchanged**, the original single-shot completion
  endpoint. `red-team/generators/llm_payload_generator.py` and any
  blue-team equivalent keep working with zero changes.
- `POST /agent/run` — the full graph. `{"task": str, "target_context":
  dict?, "max_iterations": int?}` → final state (plan, final_answer,
  status, full turn-by-turn history, timing).
- `GET /agents` — configured roles/models + live tool/memory backend status.
- `GET /memory/search?q=...&top_k=5` — reranked vector memory query.
- `GET /tasks/recent` — recent task history from the metadata store.
- `GET /metrics` — Prometheus exposition format; see `docs/observability.md`.

## Connecting this to Red/Blue's strategy generation

`red-team/generators/llm_payload_generator.py` currently calls `/generate`
for a single-shot strategy proposal. Pointing it at `/agent/run` instead
(with `target_context={"device_type": ..., "name": ...}`) would let Red
actually research a target's known weaknesses and iterate on a proposal
via the Critic before committing to an action — a natural next step, not
wired in automatically by this change, since `/generate` staying fast and
simple has value too (not every attack tick needs a full multi-agent
deliberation).
