# observability/

Prometheus + Grafana monitoring for the whole 5-laptop deployment —
system-level (CPU/mem/network/disk per laptop, via node_exporter) and
application-level (Red/Blue action rates, LLM agent latency, RL training
progress, service health, all via each service's own `/metrics`).

This is separate from `monitoring/`, which is Panopticon's own
purpose-built dashboard (the target picker, network topology, live
attack/defense feed). The two are complementary, not redundant — see
`docs/observability.md` for the full breakdown of what each one is for.

## Quick start

```bash
# On EACH of the 5 laptops:
cd observability/node_exporter && sudo ./install_node_exporter.sh

# On the Command laptop (05) only:
cd observability
docker compose up -d
```

Then open `http://command-laptop:3000` (Grafana — login `admin` /
`panopticon`, **change this password** before the lab segment is anything
but fully closed) and `http://command-laptop:9090` (Prometheus's own UI,
useful for testing PromQL queries directly).

Three dashboards are pre-provisioned under the "Project Panopticon"
folder:
- **System Overview** — CPU/mem/network/disk per laptop, service up/down
- **LLM Agent Performance** — per-role request rate, latency, mock-vs-real ratio
- **Attack & Defense Activity** — Red/Blue action rates, live service
  health/pressure gauges, RL training return/loss curves

## What's actually being scraped

See `prometheus/prometheus.yml` for the full list. Short version: every
Panopticon service mounts `/metrics` on its own existing port (no
separate metrics port to manage), and every laptop runs node_exporter on
:9100. `docs/observability.md` has the complete metric-name-to-source
mapping.

## If a target shows "down" in Grafana/Prometheus

- **referee-training** — normal between training runs; `train.py` only
  opens :9500 while actively training.
- Anything else — check that service's process is actually running on
  the laptop `prometheus.yml` expects, and that hostname resolves (see
  `deployment/switch_topology.md` for the `/etc/hosts` setup this whole
  repo assumes).
