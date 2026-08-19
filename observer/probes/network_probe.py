"""Network-level telemetry: connection counts by state and IO byte/packet
deltas for the process Observer is watching. This is the probe most likely
to actually notice something like a connection-exhaustion pattern, since
half-open/CLOSE_WAIT connections show up directly in the per-state counts.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

import psutil


@dataclass
class NetworkSample:
    pid: int
    connections_by_state: dict
    total_connections: int
    bytes_sent_delta: int
    bytes_recv_delta: int
    packets_sent_delta: int
    packets_recv_delta: int
    timestamp: float = field(default_factory=time.time)


class NetworkProbe:
    def __init__(self, pid: int):
        self.pid = pid
        self._last_io = self._read_host_io()

    def sample(self) -> NetworkSample:
        try:
            proc = psutil.Process(self.pid)
            conns = proc.net_connections(kind="inet")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            conns = []

        by_state = Counter(c.status for c in conns)

        io_now = self._read_host_io()
        bytes_sent_delta = max(0, io_now.bytes_sent - self._last_io.bytes_sent)
        bytes_recv_delta = max(0, io_now.bytes_recv - self._last_io.bytes_recv)
        packets_sent_delta = max(0, io_now.packets_sent - self._last_io.packets_sent)
        packets_recv_delta = max(0, io_now.packets_recv - self._last_io.packets_recv)
        self._last_io = io_now

        return NetworkSample(
            pid=self.pid,
            connections_by_state=dict(by_state),
            total_connections=len(conns),
            bytes_sent_delta=bytes_sent_delta,
            bytes_recv_delta=bytes_recv_delta,
            packets_sent_delta=packets_sent_delta,
            packets_recv_delta=packets_recv_delta,
        )

    @staticmethod
    def _read_host_io():
        # Per-process network IO counters aren't exposed on every platform,
        # so we fall back to host-wide counters. Inside the Arena's
        # DaemonSet (one pod per node, hostNetwork: true) the target-app is
        # effectively the dominant traffic source anyway.
        return psutil.net_io_counters()
