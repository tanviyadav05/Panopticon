"""Shapes recent telemetry into a chronological event log — what Red did,
what Blue did, and the resulting pressure/health, one row per step. This is
the data behind the dashboard's scrolling activity feed."""
from __future__ import annotations


def shape(events: list) -> dict:
    rows = [
        {
            "timestamp": e.timestamp,
            "step": e.step,
            "red_action": e.red_action,
            "blue_action": e.blue_action,
            "combined_pressure": round(e.combined_pressure, 3),
            "service_health": round(e.service_health, 3),
        }
        for e in events
    ]
    return {"rows": rows}
