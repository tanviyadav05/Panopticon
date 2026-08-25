# Troubleshooting

## Arena / Kubernetes

**`observer` pod is `CrashLoopBackOff`.**
Almost always the eBPF backend failing to load on a node without BPF
kernel support enabled, or without the `privileged: true` security context
actually being honored (some managed Kubernetes distros restrict this).
Check `kubectl -n panopticon-arena logs ds/observer`. If you see an
import or `bcc` error, that's expected on a node without `bpfcc-tools`
installed — `syscall_probe.py` is supposed to fall back to the `/proc`
backend in that case, not crash, so a crash here means the fallback
itself is failing, which usually means the container doesn't have
`/proc/<pid>/status` readable for the target PID (check the pod's PID
namespace settings, `hostPID: true` in
`arena/k8s/05-observer-daemonset.yaml`).

**`target-app` returns 500s on `/api/search`.**
If you're running against real Postgres and see this, check that the
`postgres` pod is actually ready (`kubectl -n panopticon-arena get pods`)
— `target-app`'s `ensureSchema()` only runs once at startup if Postgres
was reachable then; if Postgres came up *after* target-app, the `users`/
`orders` tables won't exist yet. Restart target-app once Postgres is
ready, or just run `arena/scripts/setup.sh` again (it waits for readiness
in the right order).

**`NetworkPolicy` doesn't seem to be blocking anything.**
If you're on Minikube: its default CNI doesn't enforce NetworkPolicy at
all — silently. You need an actual CNI that implements it (Calico is the
common choice). `kubectl get pods -n kube-system` and look for what CNI is
actually running before assuming any of `arena/k8s/04-network-policies.yaml`
or `blue-team/policies/*.yaml` are doing anything.

## Training

**`red_return` and `blue_return` are both flat lines that never move.**
Check `referee/configs/ppo_config.yaml`'s `learning_rate` — if it's been
set to 0 or something tiny by accident during a hyperparameter
experiment, both networks will barely update. Also sanity-check
`steps_per_iteration` isn't smaller than `max_steps` — if an iteration
ends mid-episode every single time, GAE's bootstrap value at the cutoff
dominates the advantage estimate.

**`evaluate.py` raises `KeyError` on a checkpoint.**
Checkpoints store `obs_dim`/`n_actions`/`hidden_size` alongside the
weights specifically so a mismatched architecture fails loudly
(`ActorCritic(payload["obs_dim"], ...)`) rather than silently loading
garbage. If you changed `RED_VISIBLE_FIELDS` in `observation_builder.py`
or `hidden_size` in `ppo_config.yaml` after a checkpoint was saved, that
checkpoint is for the old architecture — retrain, don't try to load it.

## Services

**`red_attacker.py` / `blue_controller.py` /act always returns the
no-op effect.**
Check you're sending an action *name* (`"connection_pressure"`, not
`"1"`) — both services look up actions by string key from
`common/action_spaces.py`'s lists, and an unrecognized name returns
`{"ok": false, "error": "unknown action ..."}` rather than guessing.

**`blue_controller.py`'s `isolate_pod`/`honeypot_redirect` always return
`{"ok": false, "reason": "kubernetes client/cluster unavailable"}`.**
Either the `kubernetes` package isn't installed, or no kubeconfig was
found (`KUBECONFIG` env var, or `~/.kube/config`, or it's not running
in-cluster). `rate_limit` works regardless since it's pure Python with no
cluster dependency — that's by design (see `blue-team/countermeasures/
rate_limiter.py`'s docstring) but it does mean a misconfigured kubeconfig
can silently make Blue weaker than intended without erroring loudly.
Check `GET /health`'s `cluster_available` field.

**LLM calls always return the mock backend's response even though
`LLM_BACKEND=transformers` is set.**
Environment variables set in one terminal don't propagate to a process
started from a different terminal/session. Confirm with `env | grep LLM_`
in the *exact* shell that launched `llm_server.py`, and check `GET
/health`'s `backend` field to see what's actually active.

## Multi-agent LLM stack

**`/agents` shows every agent working, but `history[].mocked` is always
`true`.**
Ollama isn't actually reachable from wherever `llm_server.py` is running.
Check `agents_config.yaml`'s `ollama.host` matches where Ollama is really
listening (`http://localhost:11434` for same-machine, `http://llm-laptop:11434`
if `llm_server.py` runs elsewhere), and confirm with `curl
$OLLAMA_HOST/api/tags` that Ollama itself responds and has the expected
models pulled. The graph runs correctly either way (that's the point of
the mock fallback — see `docs/multi_agent_llm.md`), so this won't show up
as an error, just as suspiciously generic-sounding agent output.

**`/agent/run` runs forever / takes way longer than expected.**
Check `total_steps` in the response against `max_total_steps` — if it's
sitting well under the cap, the model itself (real or mocked) may be
stuck oscillating between research and code without ever saying "done."
This is a model-quality issue, not a graph bug — the cap will still fire
eventually (default 12 steps), just possibly after more back-and-forth
than expected. Lower `graph.max_total_steps` in `agents_config.yaml` if
you want a tighter leash while iterating.

**`code_sandbox_available: false` in `/agents`, even though Docker is
installed.**
The Python `docker` package needs socket access to the daemon
(`/var/run/docker.sock` on Linux) — check the user running `llm_server.py`
is in the `docker` group, or that `DOCKER_HOST` is set correctly if
Docker's listening somewhere non-default. `code_sandbox.py` fails closed
deliberately (see its docstring) rather than falling back to running
code unsandboxed, so this is "working as intended, just not usable yet,"
not a bug to route around.

**`web_browser_available: false` even after `playwright install chromium`.**
Confirm the install actually completed (`playwright install chromium`
downloads real browser binaries — needs internet access, and can be slow
on a first run). If it did complete, re-check with `python3 -c "from
playwright.sync_api import sync_playwright; p = sync_playwright().start();
p.chromium.launch(headless=True); print('ok')"` run as the same user/env
`llm_server.py` runs under — a browser installed for one user's cache
isn't visible to another.

**Embedding/reranker logs say "using hash-fallback" / "using
lexical-overlap fallback."**
Expected without internet access to huggingface.co, or before the models
have been downloaded once — see `docs/multi_agent_llm.md`'s memory
section for the one-time download commands. The fallback isn't broken,
it's just not semantically meaningful; `/memory/search` results will look
noticeably worse (matching mostly on exact shared words) until the real
models are cached.

## Observability (Prometheus / Grafana)

**A target shows "down" in Prometheus/Grafana.**
For `referee-training`, this is normal between training runs (`train.py`
only opens :9500 while actively training). For anything else, confirm
the service's process is actually running on the laptop
`prometheus.yml` expects, and that the hostname resolves — check
`deployment/switch_topology.md`'s `/etc/hosts` setup.

**`node_exporter` fails to install / port 9100 already in use.**
Something else on that laptop is already bound to 9100. If it's an old
`referee_ingest` config from before this repo moved that port to 9600,
update whatever's still pointing at the old value — see
`deployment/inventory.yaml`'s comment on why 9100 is reserved
exclusively for node_exporter across every laptop.

**Grafana loads but panels say "No data."**
Almost always Prometheus not actually scraping that target yet — check
`http://command-laptop:9090/targets` for the target's state before
assuming the dashboard or the metric name is wrong. A freshly-started
Prometheus can take up to one `scrape_interval` (15s by default) before
a brand-new target's data appears.

**Grafana dashboards didn't load / "Project Panopticon" folder is empty.**
Check `docker compose logs grafana` for provisioning errors — most often
a JSON syntax issue in a hand-edited dashboard file under
`observability/grafana/dashboards/`. Re-run
`python3 -m json.tool < path/to/dashboard.json` to find the syntax error.

## Monitoring

**Dashboard loads but charts never move.**
Either nothing is POSTing to `/telemetry` (run with `PANOPTICON_DEMO=1`
for synthetic data, or confirm `referee/training/train.py` /
`action_executor.py` are actually configured to POST events there — this
isn't automatic; see `docs/api_documentation.md`), or the browser's
WebSocket connection failed silently. Check the browser console for the
`/ws/live` connection status — `dashboard.js` will show "disconnected —
retrying…" in the top-right status pill if so.
