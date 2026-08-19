"""Shapes recent telemetry into the network panel's series: total
connections and CLOSE_WAIT count, the two signals most likely to move
visibly under a connection-exhaustion-style pressure."""
from __future__ import annotations


def shape(events: list) -> dict:
    labels = [round(e.timestamp, 1) for e in events]
    total_connections = [e.decoded_fields.get("network.total_connections", 0.0) for e in events]
    close_wait = [e.decoded_fields.get("network.close_wait", 0.0) for e in events]
    return {"labels": labels, "total_connections": total_connections, "close_wait": close_wait}
