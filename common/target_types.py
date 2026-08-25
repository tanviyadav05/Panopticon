"""Shared target-type definitions.

Every device in the Arena has a ``DeviceType``. Two things use this:

1. ``arena/targets/*.py`` — each device class declares which type it is,
   which determines default probe methods and the RL pressure profile.
2. ``monitoring/frontend/target_picker.js`` — uses the string value to
   pick the right SVG icon for the card.

--- Attack → pressure mapping ---

We keep the same four RL pressure dimensions as before
(connection / cpu / memory / parsing) and map all new attack classes into
them. This means reward functions and the encoder don't change; only the
per-device *susceptibility multiplier* (in each device class's profile)
changes how hard each attack actually hits.

Convention: each entry is a list of (pressure_var, min_magnitude, max_magnitude) tuples.
The actual magnitude drawn per step is rng.uniform(min, max) × device susceptibility.
A susceptibility of 0.0 means the attack has no effect against this device type.
"""
from __future__ import annotations
from enum import Enum


class DeviceType(str, Enum):
    GO_APP         = "go_app"
    WIFI_ROUTER    = "wifi_router"
    WEBCAM         = "webcam"
    ANDROID_PHONE  = "android_phone"
    WINDOWS_LAPTOP = "windows_laptop"
    LINUX_LAPTOP   = "linux_laptop"
    MAC_LAPTOP     = "mac_laptop"


# Canonical mapping: attack name → [(pressure_variable, min, max), ...]
ATTACK_PRESSURE_MAP: dict[str, list] = {
    "connection_pressure":  [("connection", 0.15, 0.35)],
    "cpu_pressure":         [("cpu",        0.15, 0.35)],
    "memory_pressure":      [("memory",     0.10, 0.30)],
    "parsing_pressure":     [("parsing",    0.10, 0.25)],
    "credential_stuffing":  [("connection", 0.10, 0.25), ("cpu", 0.05, 0.15)],
    "firmware_exploit":     [("memory",     0.20, 0.40), ("parsing", 0.15, 0.30)],
    "stream_hijack":        [("connection", 0.20, 0.35), ("cpu", 0.10, 0.20)],
    "adb_exploit":          [("parsing",    0.15, 0.35), ("memory", 0.10, 0.25)],
    "smb_relay":            [("connection", 0.15, 0.30), ("parsing", 0.10, 0.25)],
    "privilege_escalation": [("cpu",        0.10, 0.25), ("memory", 0.15, 0.30)],
    "lateral_movement":     [("connection", 0.10, 0.20), ("cpu", 0.05, 0.15), ("memory", 0.05, 0.15)],
    "dns_poisoning":        [("parsing",    0.20, 0.40), ("connection", 0.05, 0.15)],
    "arp_spoof":            [("connection", 0.25, 0.45)],
    "deauth_flood":         [("connection", 0.30, 0.50)],
    "llm_generated":        [],   # magnitudes filled at runtime
}


# Per-device susceptibility multipliers.  0.0 = incompatible (noop effect).
DEVICE_SUSCEPTIBILITY: dict[str, dict[str, float]] = {
    DeviceType.GO_APP: {
        "connection_pressure": 1.0, "cpu_pressure": 1.0,
        "memory_pressure": 1.0, "parsing_pressure": 1.0,
        "credential_stuffing": 0.4, "firmware_exploit": 0.0,
        "stream_hijack": 0.0, "adb_exploit": 0.0,
        "smb_relay": 0.0, "privilege_escalation": 0.2,
        "dns_poisoning": 0.1, "arp_spoof": 0.3,
        "deauth_flood": 0.0, "lateral_movement": 0.3,
        "llm_generated": 1.0,
    },
    DeviceType.WIFI_ROUTER: {
        "connection_pressure": 0.6, "cpu_pressure": 0.4,
        "memory_pressure": 0.3, "parsing_pressure": 0.3,
        "credential_stuffing": 0.9, "firmware_exploit": 0.9,
        "stream_hijack": 0.0, "adb_exploit": 0.0,
        "smb_relay": 0.2, "privilege_escalation": 0.5,
        "dns_poisoning": 1.0, "arp_spoof": 1.0,
        "deauth_flood": 1.0, "lateral_movement": 0.4,
        "llm_generated": 1.0,
    },
    DeviceType.WEBCAM: {
        "connection_pressure": 0.7, "cpu_pressure": 0.5,
        "memory_pressure": 0.4, "parsing_pressure": 0.3,
        "credential_stuffing": 0.8, "firmware_exploit": 0.7,
        "stream_hijack": 1.0, "adb_exploit": 0.0,
        "smb_relay": 0.0, "privilege_escalation": 0.3,
        "dns_poisoning": 0.2, "arp_spoof": 0.4,
        "deauth_flood": 0.0, "lateral_movement": 0.2,
        "llm_generated": 1.0,
    },
    DeviceType.ANDROID_PHONE: {
        "connection_pressure": 0.5, "cpu_pressure": 0.4,
        "memory_pressure": 0.5, "parsing_pressure": 0.6,
        "credential_stuffing": 0.7, "firmware_exploit": 0.4,
        "stream_hijack": 0.3, "adb_exploit": 1.0,
        "smb_relay": 0.0, "privilege_escalation": 0.4,
        "dns_poisoning": 0.3, "arp_spoof": 0.5,
        "deauth_flood": 0.0, "lateral_movement": 0.3,
        "llm_generated": 1.0,
    },
    DeviceType.WINDOWS_LAPTOP: {
        "connection_pressure": 0.5, "cpu_pressure": 0.6,
        "memory_pressure": 0.6, "parsing_pressure": 0.5,
        "credential_stuffing": 0.7, "firmware_exploit": 0.1,
        "stream_hijack": 0.0, "adb_exploit": 0.0,
        "smb_relay": 1.0, "privilege_escalation": 0.9,
        "dns_poisoning": 0.3, "arp_spoof": 0.4,
        "deauth_flood": 0.0, "lateral_movement": 0.8,
        "llm_generated": 1.0,
    },
    DeviceType.LINUX_LAPTOP: {
        "connection_pressure": 0.6, "cpu_pressure": 0.7,
        "memory_pressure": 0.6, "parsing_pressure": 0.5,
        "credential_stuffing": 0.7, "firmware_exploit": 0.1,
        "stream_hijack": 0.0, "adb_exploit": 0.0,
        "smb_relay": 0.2, "privilege_escalation": 0.8,
        "dns_poisoning": 0.3, "arp_spoof": 0.4,
        "deauth_flood": 0.0, "lateral_movement": 0.8,
        "llm_generated": 1.0,
    },
    DeviceType.MAC_LAPTOP: {
        "connection_pressure": 0.5, "cpu_pressure": 0.6,
        "memory_pressure": 0.5, "parsing_pressure": 0.5,
        "credential_stuffing": 0.7, "firmware_exploit": 0.1,
        "stream_hijack": 0.1, "adb_exploit": 0.0,
        "smb_relay": 0.1, "privilege_escalation": 0.7,
        "dns_poisoning": 0.3, "arp_spoof": 0.4,
        "deauth_flood": 0.0, "lateral_movement": 0.7,
        "llm_generated": 1.0,
    },
}
