"""Memory telemetry: RSS/VMS and the rate of change between samples. Mostly
relevant for spotting memory-pressure symptoms from oversized or pathological
payloads hitting the target app.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import psutil


@dataclass
class MemorySample:
    pid: int
    rss_bytes: int
    vms_bytes: int
    memory_percent: float
    rss_delta_bytes: int
    timestamp: float = field(default_factory=time.time)


class MemoryProbe:
    def __init__(self, pid: int):
        self.pid = pid
        self._last_rss = 0

    def sample(self) -> MemorySample:
        try:
            proc = psutil.Process(self.pid)
            info = proc.memory_info()
            pct = proc.memory_percent()
            rss = info.rss
            vms = info.vms
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            rss, vms, pct = 0, 0, 0.0

        delta = rss - self._last_rss
        self._last_rss = rss

        return MemorySample(
            pid=self.pid,
            rss_bytes=rss,
            vms_bytes=vms,
            memory_percent=pct,
            rss_delta_bytes=delta,
        )
