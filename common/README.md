# common/

Shared contracts that more than one laptop's code needs to agree on
exactly — not because they run in the same process (they don't; this repo
is checked out on all five laptops, each running a different slice of it),
but because drift between two independently-maintained copies of "what
does action index 3 mean" or "what shape is the policy network" is exactly
the kind of bug that's invisible until training silently stops improving.

- `action_spaces.py` — the canonical Red/Blue action lists.
- `policy_network.py` — the actor-critic architecture used by both the
  central trainer (referee/training/) and the lightweight edge-inference
  wrappers (red-team/strategies/, blue-team/countermeasures/).

`observer/pipeline/state_schema.json` + `state_encoder.py` are the
state-side equivalent of this and intentionally live with Observer instead
(it's the producer of that contract), but referee/env/observation_builder.py
imports them from there directly — same idea, different home.
