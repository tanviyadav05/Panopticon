# MARL design

## Algorithm: Independent PPO (IPPO)

Red and Blue are each trained with their own PPO actor-critic
(`common/policy_network.py`), treating the other agent as part of the
environment rather than explicitly modeling it. This is the simplest
defensible MARL baseline — no centralized critic, no opponent modeling —
and it's enough to get a non-trivial learning signal out of this
environment. `referee/training/train.py` runs both updates per iteration,
back to back, against the same batch of rollout data.

If you want to go further: a centralized critic (each agent's value
function sees both agents' observations) or self-play-style population
training would be the natural next steps, and would mostly mean changing
`train.py`'s update step, not the environment.

## Why these reward functions

- **Red** (`referee/rewards/red_reward.py`): rewarded purely for
  `1 - service_health`, minus a tiny per-action cost. Deliberately
  agnostic to *how* Red degraded health — this keeps the reward valid
  regardless of which concrete attack module ends up wired to which
  action index.
- **Blue** (`referee/rewards/blue_reward.py`): rewarded for
  `service_health`, minus a false-positive penalty
  (`reward_utils.false_positive_cost`) for intervening when
  `true_pressure` was actually low. Without that penalty, "always isolate
  the pod" maximizes the naive reward while being a useless policy —
  the false-positive term is what makes restraint matter.

## Observation and action spaces

- **Action spaces** — `common/action_spaces.py`. Red: 6 actions (noop +
  4 pressure types + "ask the LLM"). Blue: 5 actions (noop + 4
  countermeasures).
- **Observation spaces** — asymmetric on purpose
  (`referee/env/observation_builder.py`): Blue sees the full 14-field
  telemetry vector (it's the system owner); Red sees a 7-field subset
  limited to network-level symptoms and the error rate it would
  experience directly on its own requests. Modeling this asymmetry is
  what makes Red's policy have to do something other than read Blue's
  mind.

## The simulation physics (sim mode)

`ArenaSimulation` in `panopticon_env.py` tracks four scalar "pressure"
variables (connection, cpu, memory, parsing) that Red's actions push up
and Blue's actions push down, plus natural decay each step. `service_health
= 1 - combined_pressure` drives both reward functions. It's a small,
legible model on purpose — see `docs/threat_model.md` and
`red-team/attacks/README.md` for why this is a simulation rather than a
literal attack/defense loop against the real Arena.
