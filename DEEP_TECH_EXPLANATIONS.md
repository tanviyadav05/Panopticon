# Deep technical explanations

`docs/` covers architecture, MARL design, eBPF, and the threat model each
in their own file. This document is the rest of the "why" — engineering
decisions that cut across multiple components and didn't have an obvious
single home.

## Why target-app has a `Store` interface instead of talking to Postgres directly

`arena/target-app/handlers.go` defines `Store` as an interface with both a
`memoryStore` and a `postgresStore` implementation. This isn't speculative
abstraction — it's what makes `main_test.go` able to run real tests
(`go test ./...`) without a live Postgres instance, which matters because
CI (`.github/workflows/ci.yml`) doesn't have one, and neither does a
developer's laptop before `arena/scripts/setup.sh` has been run. The
vulnerable `SearchUsers` path is identical in shape between both stores —
`BuildSearchQuery()` is called either way — so the *bug* isn't conditional
on which store is active, only whether it's actually exploitable (only
`postgresStore` executes the resulting string against a real database).

## Why Independent PPO instead of something fancier

`referee/training/train.py` trains Red and Blue as two separate PPO
agents that each treat the other as part of the environment (see
`docs/marl_design.md` for the algorithm-level rationale). The engineering
reason this mattered for a 3-day sprint specifically: IPPO is *one*
actor-critic class (`common/policy_network.py`) reused twice, one rollout
loop, one update function. A centralized-critic or self-play setup would
have meant more moving parts to get right under time pressure, for a
research platform where "the loop runs end to end and produces a
sensible-looking learning curve" mattered more than algorithmic
sophistication on day one.

## Why `common/` exists at all

Three early design mistakes this avoided, all real things that happened
while building this repo:
1. `panopticon_env.py`'s `ArenaSimulation` originally hardcoded Red's
   pressure magnitudes inline, duplicating what `red-team/attacks/*.py`
   also needed to know. Now both read from the same simulator classes.
2. The actor-critic architecture was originally defined separately in
   `referee/training/policy.py` and would have needed a second, by-hand
   copy in `red-team/strategies/attack_policy.py` for edge inference.
   `common/policy_network.py` is the one definition both load a checkpoint
   into.
3. Action index meanings (`RED_ACTIONS[3]` vs. `BLUE_ACTIONS[3]`) are easy
   to accidentally hardcode as bare integers in a hurry. `common/
   action_spaces.py` is the only place those lists are allowed to exist.

The general pattern: **if two components would otherwise need their own
copy of the same fact, that fact goes in `common/` (or, for the
state-vector contract specifically, gets imported from `observer/pipeline/`
— see that decision explained in `common/README.md`).**

## Why Red's observation is a 7-field subset, not the full 14

`referee/env/observation_builder.py`'s `RED_VISIBLE_FIELDS` list is network-
level signals plus the error rate Red would experience on its own
requests — deliberately excluding memory, raw syscall counts, and request
volume, which are internal telemetry an external attacker wouldn't have.
Without this asymmetry, Red's policy can trivially "solve" the environment
by reading signals it has no business seeing, which would make the
resulting policy meaningless as a model of anything. The asymmetry is what
makes Blue's information advantage *matter* in the reward landscape, not
just on paper.

## Why the dashboard has zero external dependencies

`monitoring/frontend/charts.js` is a hand-rolled ~70-line canvas line
chart, not Chart.js or D3 loaded from a CDN. This isn't a style
preference — `deployment/switch_topology.md` and `containment/SAFETY.md`
both specify the 5-laptop segment has no WAN uplink, so a CDN `<script src>`
would just fail silently with a blank chart. Anything served by
`dashboard_server.py` has to be genuinely self-contained.

## Why `red-team/attacks/` returns dictionaries instead of doing anything

This is covered in full in `red-team/attacks/README.md` and
`docs/threat_model.md`, but the one-sentence engineering version: every
attack module's `step()` returns `{"<pressure variable>": magnitude}` —
plain data — which `panopticon_env.py` (sim mode) or `red_attacker.py`
(live mode) interpret. There is no code path in this repository, in any
mode, where that data is converted into an actual socket, request, or
payload sent to a real target. That's a property of the *call graph*, not
a runtime flag — there's nothing to misconfigure into doing otherwise.
