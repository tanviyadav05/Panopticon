# Network topology

Two ways to connect the five laptops. Wired (a switch) is the default
this repo assumes throughout; WiFi works too, with three real
differences worth understanding before you set it up — not just "use a
router instead of a switch."

## Wired (default)

All five laptops connect to one unmanaged (or managed-but-flat) gigabit
switch. There is deliberately no router/uplink to anything else — see
`containment/SAFETY.md` for why.

```
 ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
 │ 01 · LLM   │  │ 02 · Red   │  │ 03 · Blue  │  │ 04 · Arena │  │ 05 · Command│
 │llm-core/   │  │red-team/   │  │blue-team/  │  │arena/      │  │referee/    │
 │            │  │            │  │            │  │observer/   │  │monitoring/ │
 └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
       │                │                │                │                │
       └────────────────┴────────────────┴────────────────┴────────────────┘
                                          │
                                  ┌───────┴────────┐
                                  │  Gigabit switch │
                                  │  (no WAN uplink) │
                                  └─────────────────┘
```

### IP addressing (wired)

Static IPs are simplest for a 5-machine lab segment — no DHCP server
required. Pick any private range; `inventory.yaml` uses
`192.168.50.0/24` as a placeholder. Suggested assignment:

| Laptop | Hostname        | Suggested IP      |
|--------|-----------------|--------------------|
| 01     | llm-laptop      | 192.168.50.11      |
| 02     | red-laptop      | 192.168.50.12      |
| 03     | blue-laptop     | 192.168.50.13      |
| 04     | arena-laptop    | 192.168.50.14      |
| 05     | command-laptop  | 192.168.50.15      |

Add these to `/etc/hosts` on all five machines (or run a local DNS) so the
hostnames used throughout the codebase (`llm-laptop`, `command-laptop`,
etc. — see e.g. `arena/k8s/05-observer-daemonset.yaml`'s
`REFEREE_PUBLISH_URL`) resolve correctly.

## WiFi alternative

Nothing in the application code cares whether the network under it is
wired or wireless — every service talks plain HTTP/WebSocket/TCP over
hostnames, identically either way. What actually changes going wireless
is three things, in order of how much they matter:

### 1. The closed-segment assumption is the real issue, not the cabling

`containment/SAFETY.md`'s hard requirement — no route to the internet, no
route to any other network — is what the wired switch trivially gives
you for free: an unmanaged switch has no routing function at all, so
"no WAN uplink" isn't something you configure, it's something that's
structurally true by default.

A WiFi router/AP is a **routing device**, and almost always ships with a
WAN port already carrying internet access — that's the entire point of a
home or office WiFi network. If you just join all five laptops to your
existing home/office WiFi, you have silently dropped the closed-segment
property the rest of this repo's containment posture depends on (see
`docs/threat_model.md`). This is the one change that actually matters;
everything else below is mechanical.

Two ways to keep the property:

- **Use a dedicated AP with its WAN port unplugged (or WAN function
  disabled in its admin settings), broadcasting a private SSID nobody
  else joins.** Cheapest fix if you already have a spare router: flash
  it to AP/bridge mode, or just don't connect its WAN port to anything.
  This is the wireless equivalent of "a switch with nothing else plugged
  into it," and is what makes the rest of this repo's threat model still
  apply unchanged.
- **Accept an open segment, deliberately, with the consequences
  understood.** If isolation genuinely doesn't matter for your situation
  (e.g. a personal learning sandbox with no real device targets enabled),
  that's a legitimate choice — but make it on purpose, don't back into it
  by reusing whatever WiFi happened to be nearby. See
  `docs/threat_model.md`'s containment assumptions list before deciding.

### 2. The `wifi_router` arena target and your connectivity AP shouldn't be the same device

If you're running the multi-device Arena (`docs/multi_device_targets.md`)
with `wifi_router` enabled as an attack target, and you're *also* using a
WiFi router to connect the five laptops, it's tempting to make these the
same box. Don't, if you can avoid it: that device is now simultaneously
"the thing under test" and "the thing all five laptops depend on to talk
to each other" — a materially different risk than the wired design ever
had, where the switch connecting everyone had zero attack-surface
relevance. Use two separate devices: one dedicated AP purely for laptop
connectivity (per the containment note above), one separate router as the
actual `wifi_router` target in `targets_config.yaml`. If you genuinely
can't run two devices, at minimum be explicit with yourself that they're
the same box, and treat any attack against it as something that could
disrupt the lab session's own connectivity, not just the target.

### 3. IP addressing (WiFi)

Static-IP-per-cable-port doesn't map cleanly to WiFi — laptops
associate/disassociate, and hand-configuring a static IP on a WiFi
adapter is more fragile than on a wired NIC. **DHCP reservations by MAC
address on the AP** are the more robust default for a WiFi lab segment:
look up each laptop's WiFi MAC (`ip link` / `ifconfig` on Linux,
`ipconfig /all` on Windows, `networksetup -getmacaddress` on macOS), and
reserve the same IPs from `switch_topology.md`'s wired table above for
each. The `/etc/hosts` step is identical either way.

### A smaller, real detail: probe timeouts

`arena/targets/*.py`'s device probes (ping, TCP connect, HTTP HEAD, SSH
banner, mDNS) use timeouts sized for a wired switch's low, consistent
latency. WiFi's latency is higher and considerably more variable, which
can produce false "offline" readings on an otherwise-healthy device.
Every target in `targets_config.yaml` supports
`probe_timeout_multiplier` for exactly this — see that file's comments
and `docs/multi_device_targets.md`. If the whole lab (not just the phone
and webcam, which were already WiFi-only even in the wired design) is
now wireless, set it on every entry, not only the devices that were
already wireless before.

