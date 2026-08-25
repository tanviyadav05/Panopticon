# Contributing

## Branch naming

`<initials>/<component>-<short-description>`, e.g. `tn/red-team-llm-cache-ttl`.
Matches `TEAM_ASSIGNMENTS.md`'s ownership table loosely, but anyone can
touch any component — it's a research sprint, not a strict ownership
model.

## Before opening a PR

Run the relevant subset of `make test` (see the root `Makefile`):

- Touched `arena/target-app/`? → `make test-go`
- Touched any Python component? → `make test-python` (byte-compiles
  everything; catches import errors fast) and, if you touched anything
  more than one component depends on, `make test-integration`
- Touched a `.yaml` file? → make sure it parses
  (`python3 -c "import yaml; yaml.safe_load_all(open('your_file.yaml'))"`)

The PR template (`.github/PULL_REQUEST_TEMPLATE.md`) has the full
checklist.

## Adding a new Red action

New attack classes go in `red-team/attacks/` as a simulated effect model —
see `red-team/attacks/README.md` before writing one; this isn't optional
guidance, it's the one rule in this codebase that doesn't bend for a
good reason. In practice:

1. Add a class with `name` and `step(rng) -> dict` to a new file in
   `red-team/attacks/`.
2. Add the action name to `common/action_spaces.RED_ACTIONS`.
3. Add a row to `common/target_types.ATTACK_PRESSURE_MAP` (which pressure
   variable(s) it pushes) and a susceptibility value for each device type
   in `common/target_types.DEVICE_SUSCEPTIBILITY` — 0.0 for device types
   it doesn't apply to, otherwise how strongly it applies relative to the
   others. See `docs/multi_device_targets.md`.
4. Wire it into `referee/env/panopticon_env.py`'s `_RED_SIMULATORS` dict
   and `red-team/attacks/red_attacker.py`'s `_SIMULATORS` dict (both, or
   they'll disagree between sim and live mode).
5. Update the table in `docs/threat_model.md`.

## Adding a new target device type

See `docs/multi_device_targets.md`'s "Adding an eighth device type"
section — it's a five-step checklist covering `common/target_types.py`,
a new `arena/targets/*.py` class, the registry, the dashboard icon, and
`targets_config.yaml`.

## Adding a new Blue countermeasure

Goes in `blue-team/countermeasures/` as a real implementation — unlike
Red, there's no simulation requirement here, but it does need to fail soft
(return `{"ok": false, "reason": "..."}`, don't raise) if its real
dependency (Kubernetes API, whatever) isn't available, matching the
existing pattern in `pod_isolator.py` / `honeypot_redirect.py`. Then:

1. Add the action name to `common/action_spaces.BLUE_ACTIONS`.
2. Wire it into `ArenaSimulation.apply_blue()` in `panopticon_env.py`
   (give it a sim-mode effect, even an approximate one) and
   `blue_controller.py`'s `execute()`.

## Code style

No enforced formatter/linter yet (see `.github/workflows/ci.yml` — it's a
compile/build/test check, not a style check). Match what's already in the
file you're editing. Go code should pass `go vet`.

## Documentation

If you change a contract file (`common/action_spaces.py`,
`common/policy_network.py`, `observer/pipeline/state_schema.json`), update
every consumer listed in that file's own docstring — they're listed
specifically so this is a grep-able checklist, not a memory test.
