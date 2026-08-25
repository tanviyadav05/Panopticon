# Deployment guide

For the complete, command-by-command Windows laptop runbook (including WSL2,
the unified Red/Blue/Referee GUI, local Ollama setup, Docker/K3s image
import, and least-privilege Blue kubeconfig), use
[`FIVE_LAPTOP_INSTALL.md`](FIVE_LAPTOP_INSTALL.md). This file remains the
short architecture-oriented bring-up reference.

Bring-up order matters less than you'd think — most components retry
on connection failure rather than crashing — but this order minimizes
log noise from things complaining about a dependency that isn't up yet.

## 1. Networking — wired switch or WiFi

Wire all five laptops into the switch (see `switch_topology.md`), assign
static IPs, and confirm they can ping each other by hostname before
touching any of the application code. If you're using WiFi instead, read
`switch_topology.md`'s "WiFi alternative" section first — the mechanics
are similar (DHCP reservations instead of static IPs), but there's one
real decision to make about your access point's internet uplink before
you start, not just after.

## 1.5. Configure the physical target devices

If you're attacking real devices (router, webcam, phone, extra laptops)
rather than just the Go app, join them to the same segment (switch or
WiFi — see step 1) and edit `arena/targets/targets_config.yaml` with
their actual IPs. See `docs/multi_device_targets.md` for how the registry
and probing work.

A few device-specific notes:
- **Router**: use its LAN-side management IP. If you want the optional
  SNMP read, enable a read-only public community string in its admin
  panel first. If this is also the WiFi AP connecting your five laptops,
  read `switch_topology.md`'s note on why that's worth avoiding if you can.
- **Webcam**: most consumer IP cameras default to a static or
  DHCP-reserved IP — check the manufacturer's app or your router's DHCP
  lease table.
- **Android phone**: run `adb tcpip 5555` once over USB to enable
  ADB-over-network, then note the phone's WiFi IP. See
  `docs/threat_model.md` point 6 before leaving this enabled long-term.
- **Windows/Linux/Mac laptops**: any machine on the segment works; no
  special setup is required for the non-intrusive probes in
  `arena/targets/*.py` to function (ping + TCP connect need nothing
  installed on the target).

If any of this is reached over WiFi, bump `probe_timeout_multiplier` for
that entry in `targets_config.yaml` — WiFi's latency/jitter can otherwise
produce false "offline" readings against an actually-healthy device.

Any device left unreachable is fine — it just shows as offline in the
dashboard rather than blocking anything else.

## 2. Arena laptop (04) — first

```bash
cd arena
./scripts/setup.sh
```

Confirm `kubectl -n panopticon-arena get pods` shows `target-app`,
`postgres`, `honeypot`, and an `observer` pod all Running before moving on.

## 3. LLM laptop (01)

The multi-agent stack (`docs/multi_agent_llm.md`) needs a real Ollama
daemon serving all four models. Without one, everything still runs — the
graph falls back to deterministic mock responses per agent — but you
won't get real reasoning until Ollama is actually up with the models
pulled.

```bash
# Install Ollama (see https://ollama.com), then pull the four models —
# check llm-core/config/agents_config.yaml for the exact tags this repo
# expects, and adjust the config if your local `ollama list` differs:
ollama pull hermes3:8b
ollama pull dolphin-llama3:8b
ollama pull qwen3:8b-q4_K_M     # use your imported Qwen3 7B Q4_K_M tag here if you have one

# If you want real embeddings/reranking instead of the hash/lexical
# fallback (see docs/multi_agent_llm.md), do this once with internet access:
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"
python3 -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"

# If you want the Researcher agent's web_browser tool to actually work,
# see docs/threat_model.md's "web_browser tool needs a WAN uplink"
# section BEFORE doing this — it's a deliberate exception to the closed
# lab segment, not something to do without thinking about it:
playwright install chromium

cd llm-core/server
python3 llm_server.py
```

Quick check it's wired up correctly:

```bash
curl -s localhost:8090/agents | python3 -m json.tool
curl -s -X POST localhost:8090/agent/run -H "Content-Type: application/json" \
  -d '{"task": "Summarize what this system does in one sentence."}' | python3 -m json.tool
```

If `_tools.web_browser_available` or `_tools.code_sandbox_available` come
back `false`, that's expected until you've run `playwright install
chromium` / have a Docker daemon running on this laptop respectively —
neither blocks the graph, they just mean those tools degrade to "not
available" for the Researcher/Coder agents.

## 4. Blue laptop (03)

```bash
export KUBECONFIG=/path/to/arena-laptop-kubeconfig
cd blue-team/countermeasures
python3 blue_controller.py
```

## 5. Red laptop (02)

```bash
export LLM_GATEWAY_URL=http://llm-laptop:8090
cd red-team/attacks
python3 red_attacker.py
```

## 6. Command laptop (05) — last

```bash
cd referee/training
python3 train.py   # sim mode by default; see configs/ppo_config.yaml for mode: live

# separately, the dashboard:
cd ../../monitoring
PANOPTICON_DEMO=1 python3 dashboard_server.py   # demo feed until real telemetry flows
```

Open `http://command-laptop:8000` from any machine on the switch.

## 7. Observability — Prometheus + Grafana (all laptops + Command laptop)

Compulsory monitoring layer, separate from the dashboard in step 6 — see
`docs/observability.md` for what it's for and why it's a second thing
rather than folded into `monitoring/`.

```bash
# On EACH of the 5 laptops:
cd observability/node_exporter
sudo ./install_node_exporter.sh

# On the Command laptop (05) ONLY:
cd observability
docker compose up -d
```

Open `http://command-laptop:3000` (Grafana; `admin` / `panopticon` —
change this password) and `http://command-laptop:9090` (Prometheus).
Three dashboards are pre-loaded: System Overview, LLM Agent Performance,
Attack & Defense Activity.

## Switching from sim to live training

Edit `referee/configs/ppo_config.yaml`: set `env.mode: live`, and pass an
`ActionExecutor` pointed at `http://red-laptop:8081` /
`http://blue-laptop:8082` when constructing `PanopticonEnv` (see
`action_executor.py`'s docstring) instead of the default sim-mode
construction in `train.py`. Sim mode is the recommended way to actually
train a policy (it's faster and Red's effects are simulated either way —
see `red-team/attacks/README.md`); live mode is for validating Blue's real
countermeasures against the real Arena once you have a policy you trust.
