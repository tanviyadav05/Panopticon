"""Abstract base class for all Arena target devices.
probe() — non-intrusive liveness check (ping, TCP port, HTTP HEAD, SNMP read).
simulated_attack_effect(attack, rng) — pressure dict for ArenaSimulation.
"""
from __future__ import annotations
import socket, subprocess, time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class ProbeResult:
    reachable: bool
    latency_ms: float
    open_ports: dict
    http_status: Optional[int]
    extra: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return {"reachable": self.reachable, "latency_ms": round(self.latency_ms, 2),
                "open_ports": {str(k): v for k, v in self.open_ports.items()},
                "http_status": self.http_status, "extra": self.extra, "timestamp": self.timestamp}


class BaseTarget(ABC):
    device_type: str = ""
    label: str = ""
    icon: str = "device"
    default_ports: list = []
    probe_http_path: Optional[str] = None

    def __init__(self, name: str, ip: str, **kwargs):
        self.name = name
        self.ip = ip
        self.extra_config = kwargs
        self._last_probe: Optional[ProbeResult] = None
        self._health: float = 1.0
        self.selected: bool = False
        # Scales every probe's default timeout below. 1.0 = wired-switch
        # defaults (1-2s). Bump this in targets_config.yaml for
        # WiFi-connected devices, where latency/jitter is higher and more
        # variable than a wired switch — e.g. probe_timeout_multiplier: 2.5
        # roughly doubles every probe's patience before calling a device
        # unreachable. See docs/multi_device_targets.md.
        self._timeout_multiplier = float(kwargs.get("probe_timeout_multiplier", 1.0))

    @abstractmethod
    def probe(self) -> ProbeResult: ...

    def _ping(self, timeout: float = 1.0):
        timeout *= self._timeout_multiplier
        t0 = time.monotonic()
        try:
            r = subprocess.run(["ping", "-c", "1", "-W", str(max(1, int(timeout))), self.ip],
                               capture_output=True, timeout=timeout + 1)
            return r.returncode == 0, (time.monotonic() - t0) * 1000
        except Exception:
            return False, 0.0

    def _tcp_connect(self, port: int, timeout: float = 1.0):
        timeout *= self._timeout_multiplier
        t0 = time.monotonic()
        try:
            with socket.create_connection((self.ip, port), timeout=timeout):
                return True, (time.monotonic() - t0) * 1000
        except OSError:
            return False, 0.0

    def _http_head(self, path="/", port=80, scheme="http", timeout=2.0):
        timeout *= self._timeout_multiplier
        try:
            import requests as req
            r = req.head(f"{scheme}://{self.ip}:{port}{path}", timeout=timeout,
                         allow_redirects=True, verify=False)
            return r.status_code
        except Exception:
            return None

    def update_health(self) -> float:
        result = self.probe()
        self._last_probe = result
        score = 1.0
        if not result.reachable:
            score = 0.0
        else:
            if result.latency_ms > 500: score *= 0.7
            elif result.latency_ms > 200: score *= 0.85
            open_count = sum(1 for v in result.open_ports.values() if v)
            if open_count < max(1, len(result.open_ports) // 2): score *= 0.6
        self._health = round(max(0.0, min(1.0, score)), 3)
        return self._health

    @property
    def health(self): return self._health
    @property
    def online(self): return self._last_probe is not None and self._last_probe.reachable
    @property
    def last_probe(self): return self._last_probe

    def simulated_attack_effect(self, attack_name: str, rng: np.random.Generator) -> dict:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from common.target_types import ATTACK_PRESSURE_MAP, DEVICE_SUSCEPTIBILITY
        susceptibility = DEVICE_SUSCEPTIBILITY.get(self.device_type, {}).get(attack_name, 0.0)
        if susceptibility <= 0.05 or attack_name == "noop":
            return {}
        specs = ATTACK_PRESSURE_MAP.get(attack_name, [])
        if not specs:
            key = rng.choice(["connection", "cpu", "memory", "parsing"])
            return {key: float(rng.uniform(0.20, 0.40)) * susceptibility}
        return {var: float(rng.uniform(lo, hi)) * susceptibility for var, lo, hi in specs}

    def _valid_attacks(self):
        from common.target_types import DEVICE_SUSCEPTIBILITY
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        suscep = DEVICE_SUSCEPTIBILITY.get(self.device_type, {})
        return ["noop"] + [a for a, s in suscep.items() if s > 0.05]

    def to_dict(self):
        return {"id": f"{self.device_type}:{self.name}", "device_type": self.device_type,
                "label": self.label, "icon": self.icon, "name": self.name, "ip": self.ip,
                "health": self._health, "online": self.online, "selected": self.selected,
                "last_probe": self._last_probe.to_dict() if self._last_probe else None,
                "valid_attacks": self._valid_attacks()}
