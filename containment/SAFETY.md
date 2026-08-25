# Safety / containment

This document exists so the isolation assumptions the rest of the repo
depends on are written down explicitly, not tribal knowledge. See also
`docs/threat_model.md` for the full breakdown of what's real vs.
simulated — this file is specifically about the operational containment
around the real parts.

## The hard requirement

**The 5-laptop segment must have no route to the internet, and no
route to any other network — production, home, campus, whatever — that
you'd be upset to see affected.** Not a firewall rule you trust, not a VLAN
you assume is isolated: on wired, a switch with nothing else plugged into
it; on WiFi, a dedicated AP with its WAN port unplugged or disabled. See
`deployment/switch_topology.md` for both, including why this is easy to
get right by accident when wired (a plain switch has no routing function
at all) and easy to get wrong by accident when wireless (a WiFi
router/AP almost always has internet access by default, unlike a switch).

This matters because `blue-team/`'s countermeasures are real (they call the
actual Kubernetes API — see `docs/threat_model.md`), and because
`arena/target-app` has two real, if minor, vulnerabilities by design
(`vulnerabilities.go`). Neither is dangerous *inside* an isolated segment.
Neither belongs anywhere else.

If you're running the multi-device Arena over WiFi with `wifi_router`
enabled as an attack target, see `deployment/switch_topology.md`'s note
on why that device shouldn't also be the AP connecting your five laptops
— using it for both roles means an attack on the target can disrupt the
lab's own connectivity, which the wired design never had to worry about.

## What's already enforced in code vs. what's on you

**Already enforced:**
- Red's attack modules never send real traffic (`red-team/attacks/`) — see
  `red-team/attacks/README.md`. This is true in both `sim` and `live`
  mode; nothing you set in `referee/configs/ppo_config.yaml` changes it.
- `blue-team/countermeasures/`'s Kubernetes calls fail soft (return
  `{"ok": false}`) rather than raising, so a misconfigured kubeconfig
  degrades the demo rather than doing something unexpected.

**On you:**
- The physical/network isolation described above.
- Scoping the kubeconfig you give `blue-team/` to the `panopticon-arena`
  namespace, not broader cluster access.
- Leaving `PANOPTICON_DEBUG=0` outside of active training/debugging (it's
  `1` by default in `arena/k8s/02-target-app.yaml` — see
  `docs/threat_model.md` point 3).

## The kill switch

`./killswitch.sh` is faster than `arena/scripts/cleanup.sh` (which tears
down the whole namespace) when you just need everything to *stop acting*
right now: it scales `red_attacker.py` and `blue_controller.py`'s
hosting processes to zero (or kills them, if run locally rather than via
Kubernetes) without touching the Arena's data. Use `cleanup.sh` afterward
if you actually want to tear the namespace down too.
