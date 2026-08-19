# Why these are simulations, not live attack tools

Every module in this directory models the **effect** a given attack class
would have on the target-app — a small, bounded nudge to one of the
abstract pressure variables defined in `referee/env/panopticon_env.py`
(`connection`, `cpu`, `memory`, `parsing`) — and returns that as data. None
of them open a socket, send an HTTP request, or touch the real Arena in any
way.

This is a deliberate design choice, not a missing feature:

1. **It's what published MARL cyber-defense research actually does.**
   CSIRO's CybORG and the CAGE Challenges — the closest published analogues
   to this project — represent Red's actions as abstracted effects on a
   simulated state, not literal packet-level exploits. Training against a
   simulation is also faster, more reproducible, and lets you run thousands
   of episodes without ever touching a live service.

2. **It's a line that doesn't move based on framing.** Whether the
   implementation behind a `SlowlorisSimulator.step()` call is described as
   "research," "training data generation," or "a defensive testing tool,"
   a real, working connection-exhaustion exploit is the same artifact
   either way. These modules are written so that artifact never exists in
   this codebase — `step()` returns a dictionary, not a `socket`.

If you want to test Blue's *real* countermeasures against *real* traffic
patterns, point an ordinary, separately-distributed load-testing tool
(`hey`, `wrk`, `ab`, or similar) at the target-app's Service endpoint
yourself, outside of this RL loop. That's a normal, legitimate use of those
tools against your own lab infrastructure, and it's a decision for you to
make and operate, not something this repository automates.

## The shared protocol

Each module exposes one class with:

- `name: str` — used by `strategies/attack_policy.py` and the RL action
  list to refer to it.
- `step(rng: numpy.random.Generator) -> dict` — returns `{"<pressure
  variable>": magnitude}` for the one pressure variable this attack class
  pushes on. `red_attacker.py` is the only thing that calls `step()`.
