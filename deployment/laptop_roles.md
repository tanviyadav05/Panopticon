# Laptop roles

The human-readable version of `inventory.yaml`. If you change one, change
the other.

## 01 — LLM laptop

Runs `llm-core/`. The only laptop where model weights live. Needs the most
RAM of the five if you're running real DeepSeek-R1 weights
(`LLM_BACKEND=transformers`); with the default `LLM_BACKEND=mock` it needs
almost nothing.

## 02 — Red laptop

Runs `red-team/`. Decides attack-simulation actions (via
`strategies/attack_policy.py`, once a checkpoint exists) and serves them
over HTTP for the Referee to drive during training, or operates
autonomously via its own `/decide` endpoint afterward.

## 03 — Blue laptop

Runs `blue-team/`. Mirror of Red, except its countermeasures are real:
this laptop needs a working `kubeconfig` pointed at the Arena laptop's
cluster for `isolate_pod` and `honeypot_redirect` to do anything (without
one, they fail gracefully and `rate_limit` is the only countermeasure with
teeth).

## 04 — Arena laptop

Runs `arena/` (the Kubernetes cluster hosting target-app, postgres, and the
honeypot) **and** `observer/`. Observer lives here, not on its own laptop,
because eBPF programs must attach to the kernel that's actually running the
traced process — see `referee/env/panopticon_env.py`'s module docstring and
`docs/ebpf_design.md`.

## 05 — Command laptop

Runs `referee/` (the training loop) and `monitoring/` (the live dashboard).
Also the natural place to run `analysis/` scripts once a training run has
produced checkpoints/eval logs, since they're both just reading files this
laptop already has.
