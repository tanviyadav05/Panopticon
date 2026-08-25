# Threat model

## What's real and what's simulated, exactly

This is the single most important thing to understand before running any
part of this repository against anything other than your own isolated lab
segment.

**As of the multi-device expansion, the Arena has seven target types**:
the original vulnerable Go app, plus a real WiFi router, IP webcam,
Android phone, and Windows/Linux/macOS laptops — see
`arena/targets/targets_config.yaml`. The real/simulated split below now
applies per-device, and the boundary is stricter for the new devices than
it was for the Go app, because these are appliances and personal machines,
not a throwaway container.

| Component | Real or simulated | Detail |
|---|---|---|
| `arena/target-app`'s vulnerabilities | **Real** | `vulnerabilities.go` contains an actual SQL injection and an actual path traversal. Textbook-level, same category as OWASP WebGoat/Juice Shop. |
| `arena/targets/*.py` probing (all 7 device types) | **Real, but strictly non-intrusive** | `BaseTarget.probe()` implementations do ICMP ping, TCP connect, HTTP HEAD, SSH/SNMP banner reads — reachability and metadata only. None of them authenticate, exploit, or modify device state. See `arena/targets/base_target.py`'s docstring for the exact allowed list. |
| `red-team/attacks/*.py` (all 14 named classes) | **Simulated** | Each module models the *effect* a named attack class would have (a nudge to an abstract pressure variable, scaled by `common/target_types.DEVICE_SUSCEPTIBILITY`) and returns that as data. None of them open a socket, send a request, or touch any real device — go_app, router, webcam, phone, or laptop alike. See `red-team/attacks/README.md`. |
| `blue-team/countermeasures/*.py` | **Real** | Makes actual Kubernetes API calls against whatever cluster your kubeconfig points at. Currently scoped to the Go app's namespace — see "Blue's countermeasures don't yet reach the new devices" below. |
| `observer/probes/*.py` | **Real** | Real eBPF tracepoints (or `/proc` fallback). Purely observational. |
| `llm-core/` | **Real, but advisory only** | Proposes which pressure variable to lean into — a strategy parameter, never a payload. |
| `llm-core/tools/code_sandbox.py` | **Real** | Executes Coder-agent-generated code in a real Docker container — no network access, memory-capped, wall-clock-timed. Fails closed (clear error, not a fallback to an unsandboxed subprocess) if Docker isn't available. See `docs/multi_agent_llm.md`. |
| `llm-core/tools/web_browser.py` | **Real** | Real Playwright browser automation for the Researcher agent — actually browses the internet when run on a machine with normal internet access (not this repo's isolated lab segment by default). See containment note below. |

The short version, unchanged in spirit but now covering seven device
types instead of one: **the Arena can reach out and check whether your
router/webcam/phone/laptop is alive and what ports are open. It will
never attack any of them for real, regardless of mode.**

## Why real probing but simulated attacks — the line, restated for physical devices

`arena/targets/base_target.py`'s `probe()` methods are real network calls
for the same reason a vulnerability scanner's discovery phase is real: **a
reachability check has no meaningful "blast radius."** Pinging your
router, checking if ADB-over-TCP is open on a phone, or reading a router's
public SNMP `sysDescr` string are the kind of checks any device on your
LAN is already exposed to just by being on the network — they don't
authenticate, don't send exploit payloads, and don't change anything on
the device.

`red-team/attacks/*.py` stays simulated for exactly the reason described
in `red-team/attacks/README.md`, now with higher stakes: a *working*
`deauth_flood.py` would be a functioning WiFi deauthentication tool,
usable against any 802.11 network, not just yours. A *working*
`adb_exploit.py` would be functioning Android exploitation tooling. These
aren't things this repository ships, independent of framing, independent
of which device you're pointing the simulation at.

## The web_browser tool needs a WAN uplink — a real tension with the closed-segment assumption

Every other containment assumption in this document (see below) rests on
the 5-laptop switch having **no** route to the internet. `web_browser.py`
breaks that cleanly for one specific case: if the Researcher agent is
going to do real web research, the LLM laptop needs real internet access,
which is a genuine, deliberate exception to the closed-segment rule, not
an oversight.

Two ways to resolve this, pick one before enabling the tool for real use:

1. **Keep the whole segment closed; leave `web_browser` non-functional.**
   `WebBrowser.available` will be `False` (no browser binaries installed,
   or installed but no route out), every call degrades to an empty result
   list, and the Researcher agent falls back to reasoning from its own
   knowledge. Nothing breaks; the Planner/Coder/Critic loop and the rest
   of the multi-agent stack are unaffected.
2. **Give the LLM laptop (and only the LLM laptop) a real, separate
   uplink** — its own interface/NIC on a different network than the
   switch the other four laptops share, not a bridge that would quietly
   extend internet reachability to Red or the Arena. Don't just remove
   the "no WAN uplink" rule for the whole segment to make this one tool
   work.

Either way, `code_sandbox.py`'s Docker containers stay `network_disabled`
regardless of what the host laptop's own connectivity looks like — that
isolation is enforced per-container, not by the network topology around
it, so it doesn't change based on which option above you pick.

## Blue's countermeasures don't yet reach the new devices

`blue-team/countermeasures/pod_isolator.py` and `honeypot_redirect.py`
are Kubernetes-API calls, which means they're meaningful against
`target-app` (a pod) but not against a physical router, webcam, or phone
— there's no Kubernetes object representing "isolate the WiFi router."
`rate_limit`'s `TokenBucket` is pure Python and technically applies to
anything, but doesn't yet have a real enforcement point for non-Kubernetes
devices (no iptables/firewall integration is wired in). Practically: when
attacking the new device types in `live` mode, Blue's `isolate_pod` and
`honeypot_redirect` actions will fail soft (`{"ok": false}`) rather than
doing something real — this is intentional graceful degradation, not a
bug, but it does mean Blue is currently more bark than bite against
anything that isn't the Go app. Extending real containment to the other
device types (router: push an ACL via its admin API; phone: MDM policy
push; laptops: host firewall rule via SSH) is listed as an open item in
`CONTRIBUTING.md`.

## Why that asymmetry, specifically

Blue's actions (rate-limiting, cordoning a pod, redirecting traffic) are
defensive operations with an obvious, bounded blast radius even if
misapplied — worst case, you've rate-limited or restarted your own toy
app. Red's actions, if implemented for real, would be working
denial-of-service/exploit tooling. That category of artifact isn't
something this repository ships, independent of the research framing —
see `red-team/attacks/README.md` for the longer version of this argument.
Training against simulated Red effects is also standard practice in
published MARL cyber-defense research (CybORG, the CAGE Challenges), so
this isn't a capability gap relative to that literature, just a different
implementation of the same idea.

## What the vulnerable app's flaws represent

`vulnerabilities.go`'s SQL injection and path traversal are both
*data-exposure* bugs — the worst realistic outcome is "the wrong rows came
back" or "a file outside the intended directory got read." Neither is a
remote-code-execution primitive. That's deliberate: it keeps the Arena's
worst case bounded even if `PANOPTICON_DEBUG=1` is left on and someone
points a real scanner at it.

## Containment assumptions everything else depends on

1. **The 5-laptop segment (wired or WiFi) has no route to the internet or
   to any other network you care about.** See
   `deployment/switch_topology.md` and `containment/SAFETY.md` — the WiFi
   case is worth reading closely even if you're used to the wired setup,
   since a WiFi router/AP has internet access by default in a way a plain
   switch structurally can't. The one deliberate, narrow exception is
   `llm-core/tools/web_browser.py` if you choose to enable it — see "The
   web_browser tool needs a WAN uplink" above for how to do that without
   quietly reopening the whole segment.
2. **Blue's real Kubernetes actions are scoped to the `panopticon-arena`
   namespace** via the kubeconfig/RBAC you give `blue-team/` — don't point
   it at a kubeconfig with broader cluster access than that.
3. **`PANOPTICON_DEBUG=1`** (set by default in
   `arena/k8s/02-target-app.yaml`, for training visibility) surfaces the
   raw vulnerable query string and file path in API responses. Turn it off
   for anything you wouldn't hand a stranger a shell-adjacent debug
   console for.
4. **`red-team/attacks/` stays simulated.** If you fork this repo and
   change that, you've changed what this threat model describes — treat
   it as a different project with its own containment requirements, not
   an extension of this one.
5. **The physical devices in `arena/targets/targets_config.yaml` should be
   ones you own or have explicit permission to point probes at**, even
   though those probes are non-intrusive. Pinging or port-scanning a
   device you don't control — even harmlessly — isn't something this
   threat model clears you to do; that permission is on you, the same way
   it would be before running any network scanner.
6. **The Android phone's ADB-over-TCP (`adb tcpip 5555`) should only be
   enabled on a device dedicated to this lab.** Leaving ADB open over the
   network is a real, standing exposure independent of anything this
   repo does with it — treat enabling it as a deliberate, temporary lab
   setup step, not a phone you carry around afterward with ADB still on.

## Out of scope

This threat model is about Panopticon's own design. It is not a general
security assessment of Kubernetes, eBPF, or any of the libraries this
repo depends on (Postgres, FastAPI, scikit-learn, etc.) — keep those
patched the normal way.
