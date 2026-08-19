"""Buffers raw Observer ticks into fixed time windows and reduces each
window to one flat summary dict, so downstream consumers (state_encoder)
get a steady stream of summaries instead of the raw per-tick firehose.

Reduction rule per field:
  * counts/deltas (connections, bytes, syscalls, http requests) -> summed
  * gauges (rss bytes, cpu percent, error rate)                  -> averaged
  * flags (alive, restart_detected)                               -> max (if
    it happened even once in the window, the window reports it)
"""
from __future__ import annotations

import time
from typing import Optional


_SUM_FIELDS = {
    "network.bytes_sent_delta", "network.bytes_recv_delta",
    "memory.rss_delta_bytes", "syscall.syscalls_per_interval",
    "http.requests_per_window",
}
_MAX_FIELDS = {"process.restart_detected"}
_MIN_FIELDS = {"process.alive"}  # 0 if it was ever down during the window


class Aggregator:
    def __init__(self, window_seconds: float = 1.0):
        self.window_seconds = window_seconds
        self._buffer: list[dict] = []
        self._window_start: Optional[float] = None

    def add(self, event: dict) -> Optional[dict]:
        """Add one raw tick. Returns a flushed window summary if the window
        just closed, otherwise None."""
        now = event.get("timestamp", time.time())
        if self._window_start is None:
            self._window_start = now

        self._buffer.append(event)

        if now - self._window_start >= self.window_seconds:
            summary = self.flush()
            self._window_start = now
            return summary
        return None

    def flush(self) -> dict:
        if not self._buffer:
            return {}

        flat_events = [self._flatten(e) for e in self._buffer]
        keys = set()
        for fe in flat_events:
            keys.update(fe.keys())

        summary = {}
        for key in keys:
            values = [fe.get(key, 0) for fe in flat_events]
            if key in _SUM_FIELDS:
                summary[key] = sum(values)
            elif key in _MAX_FIELDS:
                summary[key] = max(values)
            elif key in _MIN_FIELDS:
                summary[key] = min(values)
            else:
                summary[key] = sum(values) / len(values)  # average by default

        summary["window_event_count"] = len(self._buffer)
        summary["window_seconds"] = self.window_seconds
        self._buffer = []
        return summary

    @staticmethod
    def _flatten(event: dict) -> dict:
        flat = {}

        def walk(node, prefix):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{prefix}.{k}" if prefix else k)
            elif isinstance(node, (int, float, bool)):
                flat[prefix] = float(node)
            # strings/None are dropped — the encoder only deals in numbers

        walk(event, "")
        return flat
