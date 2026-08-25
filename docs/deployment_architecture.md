# Deployment architecture

See `deployment/switch_topology.md`, `deployment/laptop_roles.md`, and
`deployment/inventory.yaml` for the operational version of this document —
this one exists in `docs/` because it's the version meant to sit next to
`architecture.md` and `threat_model.md` for anyone reading the docs/
folder end to end (e.g. for a report or writeup) rather than following
along step by step.

## Summary

| # | Role | Runs | Real or simulated effects |
|---|------|------|---------------------------|
| 01 | LLM | `llm-core/` | N/A (advisory only) |
| 02 | Red | `red-team/` | **Simulated** — see `red-team/attacks/README.md` |
| 03 | Blue | `blue-team/` | **Real** — calls the actual Kubernetes API |
| 04 | Arena | `arena/`, `observer/` | Real — actual vulnerable app, actual eBPF telemetry |
| 05 | Command | `referee/`, `monitoring/` | N/A (orchestration + dashboard) |

The asymmetry in the rightmost column — Blue is real, Red is simulated —
is the single most important fact about this deployment and is covered in
full in `threat_model.md`.

## Single-laptop development mode

You don't need all five laptops to develop against this repo. Everything
under `referee/` runs standalone in `mode: sim` on one machine with no
network at all (that's what `referee/training/train.py` does by default).
`monitoring/`'s `PANOPTICON_DEMO=1` flag likewise drives the dashboard from
the same self-contained simulation. The 5-laptop deployment is for running
Blue's countermeasures against a real cluster and for the live dashboard
showing real Arena telemetry — not a prerequisite for training or testing
the RL side of the system.
