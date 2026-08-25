# Architecture

Project Panopticon has five components, each owned by one of the five
laptops (see `deployment/laptop_roles.md`):

```
Arena (04) ──telemetry──► Observer (04, same laptop) ──state──► Referee (05)
                                                                    │  │
                                              actions ◄─────────────┘  └──► Monitoring (05)
                                                │
                    ┌───────────────────────────┴───────────────────────────┐
                    ▼                                                       ▼
              Red laptop (02)                                       Blue laptop (03)
         red-team/ (simulated effects,                        blue-team/ (real countermeasures,
         see attacks/README.md)                                real Kubernetes API calls)
                    │                                                       │
                    └───────────────► both query ◄────────────────────────┘
                                  LLM Core (01)
```

## The control loop vs. the data plane

Two different kinds of connection cross laptop boundaries:

- **Control loop** (solid lines in the diagram the repository guide draws):
  Observer → Referee (encoded state), Referee → Red/Blue (chosen actions).
  This is what `referee/env/action_executor.py` owns in live mode, and what
  `referee/env/panopticon_env.py`'s internal `ArenaSimulation` replaces
  entirely in sim mode.
- **Data plane**: Red/Blue → Arena (apply an effect), Red/Blue → LLM Core
  (ask for a strategy). These happen regardless of training mode.

## Why two modes (sim / live)

`referee/env/panopticon_env.py` supports `mode="sim"` (the default, and
what `referee/training/train.py` actually trains against) and
`mode="live"`. Sim mode is fully self-contained — no other laptop needs to
be running — and is what makes the PPO loop fast enough to iterate on.
Live mode wires in the real Arena and real Blue countermeasures; Red's
actions stay simulated either way (see `docs/threat_model.md` for why).

## State and action contracts

Two small "never let these drift" contracts hold the whole multi-laptop
system together:

- `observer/pipeline/state_schema.json` + `state_encoder.py` — the shape of
  the telemetry vector.
- `common/action_spaces.py` — what action index N means for each agent.

Both are described in more depth in `docs/api_documentation.md`.
