"""Process lifecycle telemetry. A crash-restart loop on target-app shows up
here first: the PID changes (the old one died and Kubernetes started a new
one) before any other probe necessarily notices something was wrong.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import psutil


@dataclass
class ProcessSample:
    pid: int
    alive: bool
    uptime_seconds: float
    restart_detected: bool
    cpu_percent: float
    timestamp: float = field(default_factory=time.time)


class ProcessProbe:
    def __init__(self, pid: int, process_name: str):
        self.process_name = process_name
        self.pid = pid
        self.restart_count = 0
        self._create_time = self._safe_create_time(pid)

    def sample(self) -> ProcessSample:
        current_pid = self._resolve_pid()
        restart = False

        if current_pid is None:
            alive = False
            uptime = 0.0
            cpu = 0.0
        else:
            if current_pid != self.pid:
                restart = True
                self.restart_count += 1
                self.pid = current_pid
                self._create_time = self._safe_create_time(current_pid)

            alive = True
            uptime = max(0.0, time.time() - (self._create_time or time.time()))
            try:
                cpu = psutil.Process(current_pid).cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cpu = 0.0

        return ProcessSample(
            pid=self.pid,
            alive=alive,
            uptime_seconds=uptime,
            restart_detected=restart,
            cpu_percent=cpu,
        )

    def _resolve_pid(self) -> Optional[int]:
        # Prefer the pid we already know about if it's still alive...
        if psutil.pid_exists(self.pid):
            try:
                if self.process_name.lower() in psutil.Process(self.pid).name().lower():
                    return self.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # ...otherwise look for a process with a matching name (a restart).
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if self.process_name.lower() in (proc.info["name"] or "").lower():
                    return proc.info["pid"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    @staticmethod
    def _safe_create_time(pid: Optional[int]) -> Optional[float]:
        if pid is None:
            return None
        try:
            return psutil.Process(pid).create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
