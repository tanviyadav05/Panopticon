"""Canonical action lists — 16 Red actions covering all 7 device types."""

RED_ACTIONS = [
    "noop",
    "connection_pressure",
    "cpu_pressure",
    "memory_pressure",
    "parsing_pressure",
    "credential_stuffing",
    "firmware_exploit",
    "stream_hijack",
    "adb_exploit",
    "smb_relay",
    "privilege_escalation",
    "dns_poisoning",
    "arp_spoof",
    "deauth_flood",
    "lateral_movement",
    "llm_generated",
]

BLUE_ACTIONS = [
    "noop",
    "rate_limit",
    "isolate_pod",
    "honeypot_redirect",
    "raise_alert_threshold",
]

RED_NOOP_INDEX  = RED_ACTIONS.index("noop")
BLUE_NOOP_INDEX = BLUE_ACTIONS.index("noop")


def valid_attacks_for(device_type: str) -> list:
    """Returns action names whose susceptibility > 0.05 for this device type."""
    import os, sys
    _common = os.path.dirname(os.path.abspath(__file__))
    if _common not in sys.path:
        sys.path.insert(0, _common)
    from target_types import DEVICE_SUSCEPTIBILITY
    suscep = DEVICE_SUSCEPTIBILITY.get(device_type, {})
    return ["noop"] + [a for a in RED_ACTIONS[1:] if suscep.get(a, 0.0) > 0.05]
