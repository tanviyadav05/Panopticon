"""Shapes recent telemetry into whatever charts.js expects for the CPU
panel: parallel label/value arrays, newest last."""
from __future__ import annotations


def shape(events: list) -> dict:
    labels = [round(e.timestamp, 1) for e in events]
    cpu_values = [e.decoded_fields.get("process.cpu_percent", 0.0) for e in events]
    return {"labels": labels, "cpu_percent": cpu_values}
