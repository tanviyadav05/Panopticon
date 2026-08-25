# Multi-device targets

The Arena expanded from one vulnerable Go app to seven target device
types: the original app, plus a real WiFi router, IP webcam, Android
phone, and Windows/Linux/macOS laptops. This document covers the pieces
specific to that expansion — read `docs/threat_model.md` first for the
real-vs-simulated boundary, which this builds on.

## The three new pieces

**`arena/targets/`** — one class per device type
(`wifi_router.py`, `webcam.py`, `android_phone.py`, `windows_laptop.py`,
`linux_laptop.py`, `mac_laptop.py`, plus the original app as
`go_app_target.py`), all inheriting from `base_target.py`. Each
implements `probe()` — a real, non-intrusive liveness/port check — and
inherits `simulated_attack_effect()`, which looks up
`common/target_types.DEVICE_SUSCEPTIBILITY` to scale a simulated attack's
magnitude for that specific device type. Every probe's timeout scales
with that device's `probe_timeout_multiplier` (set per-entry in
`targets_config.yaml`, default 1.0) — worth raising for anything reached
over WiFi rather than a wired switch; see
`deployment/switch_topology.md`'s WiFi section.

**`common/target_types.py`** — the susceptibility matrix: for every
(attack, device_type) pair, a multiplier in [0, 1]. `deauth_flood` is
`1.0` against a `wifi_router` and `0.0` against `go_app` — the attack
simply doesn't apply. This is what makes attacking the "wrong" device for
a given technique produce near-zero pressure instead of a nonsensical
generic effect.

**`arena/targets/target_registry.py`** — a process-wide singleton that
loads `targets_config.yaml`, runs a background thread probing every
enabled device on an interval (default 10s), and tracks which device is
currently "active" (selected for attack). `monitoring/telemetry_api.py`
imports this registry directly; `referee/env/panopticon_env.py` doesn't
touch it at all — the RL loop takes a `target_device_type` string, it
doesn't know or care that a registry/dashboard exists.

## How a device gets attacked

1. Someone clicks a device card in the dashboard (or POSTs
   `/targets/select` directly).
2. `target_registry.select()` updates the active device.
3. Whoever's driving the RL loop — `train.py`, the demo feed in
   `dashboard_server.py`, or a live-mode `action_executor.py` — reads
   `registry.active.device_type` and passes it as
   `PanopticonEnv(target_device_type=...)` or via
   `env.reset(options={"target_device_type": ...})` mid-run.
4. `ArenaSimulation.apply_red()` looks up that device type's
   susceptibility for whatever attack the policy chose, and scales the
   pressure effect accordingly.

The registry and the RL environment are deliberately decoupled — nothing
in `referee/` imports `arena/targets/`. The dashboard is what bridges
them, by reading the registry and telling the environment which device
type is active.

## The dashboard target picker

`monitoring/frontend/target_picker.js` renders one card per registered
device (icon, name, IP, live health bar, online/offline dot, and a few
attack-compatibility tags), reading from `GET /targets`. Clicking a card:

- Optimistically highlights it client-side
- POSTs `/targets/select`
- The server-authoritative state comes back over the WebSocket's
  `targets_update` messages (every ~3s, plus immediately on connect)

`monitoring/frontend/network_map.js` draws a small SVG topology — the 5
Panopticon laptops on the left, a switch in the middle, all registered
target devices on the right, colored by live health (green/amber/red/grey
for healthy/degraded/critical/offline) with a pulsing ring on whichever
device is currently selected.

## Adding an eighth device type

1. Add a `DeviceType` entry and a `DEVICE_SUSCEPTIBILITY` row in
   `common/target_types.py` — one multiplier per existing attack.
2. Create `arena/targets/your_device.py` extending `BaseTarget`, with a
   real `probe()` (non-intrusive only — see `base_target.py`'s docstring
   for what's allowed).
3. Register it in `arena/targets/target_registry.py`'s
   `_import_device_classes()`.
4. Add an icon to `ICON_MAP`/`ICONS` in
   `monitoring/frontend/target_picker.js` and a CSS accent color in
   `styles.css`'s `.device-card[data-type="..."]` rules.
5. Add an entry to `arena/targets/targets_config.yaml`.

No changes needed in `referee/`, `red-team/`, or `common/action_spaces.py`
— the action space is per-attack, not per-device, so a new device type
just needs a new susceptibility row, not new actions.
