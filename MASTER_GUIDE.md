# Master guide

Start here. Everything below links to the file that actually explains the
thing in depth — this document is the map, not the territory.

## What this is

Project Panopticon is a multi-agent reinforcement learning cyber range:
an autonomous Red agent and an autonomous Blue agent learn, via PPO,
to attack and defend a deliberately-vulnerable Go service running in
Kubernetes, while a local LLM advises both sides and an eBPF-based
Observer watches everything at the kernel level. See `docs/architecture.md`
for the full picture.

**Read `docs/threat_model.md` before running anything against a real
cluster.** Short version: Blue's countermeasures are real (they call the
actual Kubernetes API); Red's attacks are simulated effects, not live
exploit code, in every mode. This is explained in full there and in
`red-team/attacks/README.md`.

## Fastest path to seeing it work (one laptop, no cluster)

```bash
pip install -r requirements.txt --break-system-packages
cd referee/training
python3 train.py --iterations 5          # trains both agents in sim mode, ~30s
python3 evaluate.py --episodes 10 --out /tmp/eval.json
cd ../../analysis
python3 generate_report.py --log /tmp/eval.json --out /tmp/report.html
```

Open `/tmp/report.html`. That's the whole RL loop, no Kubernetes, no LLM,
no other laptop required.

To see the live dashboard with the same self-contained simulation driving
it:

```bash
cd monitoring
PANOPTICON_DEMO=1 python3 dashboard_server.py
# open http://localhost:8000
```

## The real 5-laptop deployment

See `deployment/deployment_guide.md` for the step-by-step bring-up order,
`deployment/laptop_roles.md` for who runs what, and
`TEAM_ASSIGNMENTS.md` for who owns what.

## Where to go deeper

| Question | Document |
|---|---|
| How do the five components fit together? | `docs/architecture.md` |
| Why these reward functions / this action space? | `docs/marl_design.md` |
| Why eBPF, and why does Observer live on the Arena laptop? | `docs/ebpf_design.md` |
| What's real vs. simulated, and why? | `docs/threat_model.md` |
| How does the multi-device target picker work? | `docs/multi_device_targets.md` |
| How does the multi-agent LLM stack work? | `docs/multi_agent_llm.md` |
| How does Grafana/Prometheus monitoring work? | `docs/observability.md` |
| What does every single file in the repo hold? | `DEEP_TECH_EXPLANATIONS.md` |
| Something's broken | `TROUBLESHOOTING.md` |
| I want to add an attack class / countermeasure / contribute | `CONTRIBUTING.md` |
