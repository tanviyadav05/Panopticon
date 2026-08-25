# Team assignments

The human ↔ laptop ↔ component mapping. If you're new to the team, this
plus `deployment/laptop_roles.md` is everything you need to know which
machine to sit at.

| Owner | Focus | Laptop | Components |
|---|---|---|---|
| **Astitva** | Project lead, architecture, MARL orchestration | 05 — Command | `referee/`, overall integration |
| **Kushal** | AI/ML | 01 — LLM, plus `referee/training/` | `llm-core/`, the PPO training loop |
| **Tanvi** | Attack | 02 — Red | `red-team/` |
| **Shreya** | Defense | 03 — Blue | `blue-team/` |
| **Nitesh** | Infrastructure | 04 — Arena | `arena/`, `observer/`, `.github/workflows/`, `deployment/` |

## Cross-cutting ownership

A few things don't belong to one laptop and are everyone's responsibility
to keep in sync (see each file's own docstring for why):

- `common/action_spaces.py` and `common/policy_network.py` — touch these
  and you've touched Red, Blue, *and* the trainer.
- `observer/pipeline/state_schema.json` — touch this and you've touched
  Observer's encoder *and* Referee's `observation_builder.py`.
- `docs/threat_model.md` — whoever adds a new Red action class or Blue
  countermeasure should update the table here, not just the code.

## Mid-evaluation sprint structure

For a tight deadline (the original 3-day mid-eval sprint this codebase was
built under), the natural split is: Nitesh gets the Arena up first (Day 1
morning) since everyone else needs it before parallelizing; Kushal and
Astitva pair on the env/reward/training loop in sim mode while Tanvi and
Shreya build their respective services against it; integration (live mode,
or at least Blue-against-real-Arena) happens last once each piece works in
isolation.
