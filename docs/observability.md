# Observability (Prometheus + Grafana)

Grafana monitoring for the whole 5-laptop deployment, both system-level
(CPU/mem/network/disk per laptop) and application-level (attack/defense
activity, LLM agent performance, RL training progress).

## Why this exists alongside `monitoring/`

Two dashboards, two different jobs — this isn't duplication:

| | `monitoring/` (existing) | `observability/` (this) |
|---|---|---|
| Built for | Panopticon's own domain — the target picker, live topology, attack feed | Generic infra monitoring — Prometheus + Grafana |
| Shows | Which device is being attacked right now, with what, and its live health | System resource usage across all 5 laptops, service uptime, historical trends |
| Data lifetime | In-memory, resets on restart | Persisted (30-day retention by default) |
| Interaction | Click a device to attack it | Read-only dashboards, PromQL exploration |

Use `monitoring/` to *run* an attack/defense session. Use this to *watch
the infrastructure* while you do, and to look back at trends across
multiple sessions.

## Architecture

```
  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
  │ 01 LLM      │    │ 02 Red      │    │ 03 Blue     │    │ 04 Arena    │    │ 05 Command  │
  │             │    │             │    │             │    │             │    │             │
  │ llm-core    │    │ red-team    │    │ blue-team   │    │ target-app  │    │ dashboard   │
  │ :8090/metrics│    │:8081/metrics│    │:8082/metrics│    │ :80/metrics │    │:8000/metrics│
  │             │    │             │    │             │    │             │    │ train.py    │
  │ node_exp    │    │ node_exp    │    │ node_exp    │    │ node_exp    │    │:9500/metrics│
  │ :9100       │    │ :9100       │    │ :9100       │    │ :9100       │    │ node_exp    │
  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    │ :9100       │
         │                  │                   │                  │           │             │
         └──────────────────┴───────────────────┴──────────────────┴──────────▶│ Prometheus  │
                                                                                 │ :9090       │
                                                                                 │      │      │
                                                                                 │      ▼      │
                                                                                 │  Grafana    │
                                                                                 │  :3000      │
                                                                                 └─────────────┘
```

Prometheus and Grafana both run in `observability/docker-compose.yml`,
**only on the Command laptop (05)**. node_exporter runs natively (not in
a container) on **all five** laptops — see
`observability/node_exporter/install_node_exporter.sh` and its docstring
for why this can't be centralized.

## What's exposed where

Every Panopticon service mounts `/metrics` on its own existing app port —
no separate metrics port to remember or firewall. Full scrape list in
`observability/prometheus/prometheus.yml`; the key metric names:

| Service | Key metrics |
|---|---|
| `arena/target-app` (Go) | `target_app_requests_total`, `target_app_errors_total`, `target_app_requests_by_path_total` — hand-rolled Prometheus format, see `middleware.go` |
| `llm-core` | `llm_core_agent_turns_total{agent,mocked}`, `llm_core_agent_run_latency_seconds`, `llm_core_generate_latency_seconds` |
| `red-team` | `panopticon_red_actions_total{action,target_device_type}` |
| `blue-team` | `panopticon_blue_actions_total{action,ok}`, `panopticon_blue_anomaly_score` |
| `monitoring` dashboard | `panopticon_telemetry_events_total`, `panopticon_service_health` (gauge), `panopticon_combined_pressure` (gauge) |
| `referee/training/train.py` | `panopticon_train_iteration`, `panopticon_train_{red,blue}_return`, `panopticon_train_{red,blue}_policy_loss` — **only up while a training run is actively in progress** |
| every laptop | `node_cpu_seconds_total`, `node_memory_*`, `node_network_*`, `node_filesystem_*` (standard node_exporter) |

`common/metrics.py` is the shared helper every Python service uses —
`mount_metrics(app)` adds the `/metrics` route, `counter()` /
`histogram()` / `gauge()` are thin factories over `prometheus_client` so
every service defines metrics the same way.

## Dashboards

Three, pre-provisioned (`observability/grafana/dashboards/*.json`, loaded
automatically on Grafana startup — no manual import):

1. **System Overview** — CPU/mem/network/disk per laptop, service up/down
   status at a glance.
2. **LLM Agent Performance** — per-role turn rate, mocked-vs-real ratio
   (a `1.0` ratio for more than a few minutes means Ollama isn't actually
   reachable — see Troubleshooting), `/generate` and `/agent/run` latency
   percentiles.
3. **Attack & Defense Activity** — live service health / combined
   pressure gauges, Red actions by type and by target device, Blue action
   success rate, RL training return/loss curves.

All are ordinary Grafana dashboards after provisioning — edit, clone, or
add panels through the UI same as any other; the JSON files are just the
starting point, not something you're meant to hand-edit going forward.

## Alerts

`observability/prometheus/alerts.yml` — deliberately small: service-down,
elevated target-app error rate, llm-core running almost entirely on mock
fallback (a real sign Ollama isn't reachable), and sustained critical
service health. Without Alertmanager wired in, these just show red in
Prometheus's and Grafana's own alert views — enough for a lab setup where
someone's actually watching the screen.

## Setup

See `observability/README.md` for the actual commands. Short version:
`install_node_exporter.sh` on all five laptops, `docker compose up -d`
in `observability/` on the Command laptop only.
