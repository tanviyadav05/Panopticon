"""Orchestrates syscall/network/memory/process probes as one service.

Usage (standalone, for local testing — prints raw ticks, no aggregation):

    python3 probes/observer.py --process-name target-app --interval 1.0

Usage (production — aggregates, encodes, and publishes to the Referee):

    REFEREE_PUBLISH_URL=http://command-laptop:9600/ingest python3 probes/observer.py

In the real Arena deployment this runs inside the observer DaemonSet
(arena/k8s/05-observer-daemonset.yaml), which sets both
TARGET_PROCESS_NAME and REFEREE_PUBLISH_URL — see main()'s docstring for
exactly which path that env var selects.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import re
import sys
import time
from typing import Callable, Optional

import psutil
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # -> observer/

from probes.memory_probe import MemoryProbe
from probes.network_probe import NetworkProbe
from probes.process_probe import ProcessProbe
from probes.syscall_probe import SyscallProbe
from pipeline.aggregator import Aggregator
from pipeline.state_encoder import StateEncoder
from pipeline.publisher import Publisher


_METRIC_LINE = re.compile(r'^(?P<name>\w+)(\{[^}]*\})?\s+(?P<value>[0-9.eE+-]+)\s*$')


class HttpMetricsScraper:
    """Pulls target-app's Prometheus-text /metrics and turns the running
    counters into per-tick deltas (requests_per_window, error_rate)."""

    def __init__(self, metrics_url: str, timeout: float = 0.5):
        self.metrics_url = metrics_url
        self.timeout = timeout
        self._last_total = 0
        self._last_errors = 0

    def sample(self) -> dict:
        totals = {"target_app_requests_total": 0, "target_app_errors_total": 0}
        try:
            resp = requests.get(self.metrics_url, timeout=self.timeout)
            for line in resp.text.splitlines():
                m = _METRIC_LINE.match(line.strip())
                if m and m.group("name") in totals:
                    totals[m.group("name")] = float(m.group("value"))
        except requests.RequestException:
            pass  # target-app unreachable this tick; report a zero-activity window

        total = totals["target_app_requests_total"]
        errors = totals["target_app_errors_total"]
        requests_delta = max(0, total - self._last_total)
        errors_delta = max(0, errors - self._last_errors)
        self._last_total, self._last_errors = total, errors

        return {
            "requests_per_window": requests_delta,
            "error_rate": (errors_delta / requests_delta) if requests_delta else 0.0,
        }


def find_pid_by_name(process_name: str) -> Optional[int]:
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if process_name.lower() in (proc.info["name"] or "").lower():
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


class Observer:
    def __init__(self, process_name: str, pid: Optional[int] = None, metrics_url: Optional[str] = None):
        self.process_name = process_name
        resolved_pid = pid or find_pid_by_name(process_name) or os.getpid()
        self.process_probe = ProcessProbe(resolved_pid, process_name)
        self.network_probe = NetworkProbe(resolved_pid)
        self.memory_probe = MemoryProbe(resolved_pid)
        self.syscall_probe = SyscallProbe(resolved_pid)
        self.http_scraper = HttpMetricsScraper(metrics_url) if metrics_url else None

    def tick(self) -> dict:
        """One round of sampling across all probes, merged into a single
        raw event. If the process restarted since the last tick (detected
        by process_probe), the network/memory/syscall probes are re-pointed
        at the new pid so they don't keep reporting on a dead process."""
        proc_sample = self.process_probe.sample()
        if proc_sample.restart_detected:
            self.network_probe.pid = proc_sample.pid
            self.memory_probe.pid = proc_sample.pid
            self.syscall_probe.pid = proc_sample.pid

        net_sample = self.network_probe.sample()
        mem_sample = self.memory_probe.sample()
        sys_sample = self.syscall_probe.sample()
        http_sample = self.http_scraper.sample() if self.http_scraper else {"requests_per_window": 0, "error_rate": 0.0}

        return {
            "timestamp": time.time(),
            "pid": proc_sample.pid,
            "process": dataclasses.asdict(proc_sample),
            "network": dataclasses.asdict(net_sample),
            "memory": dataclasses.asdict(mem_sample),
            "syscall": dataclasses.asdict(sys_sample),
            "http": http_sample,
        }

    def run(self, interval: float, on_event: Callable[[dict], None], iterations: Optional[int] = None):
        count = 0
        while iterations is None or count < iterations:
            on_event(self.tick())
            count += 1
            time.sleep(interval)

    def close(self):
        self.syscall_probe.close()


def main():
    """Two modes, selected by whether --publish-url (or REFEREE_PUBLISH_URL)
    is set:

    - **Unset** (local/standalone use): prints each raw tick to stdout.
      Nothing is aggregated, encoded, or sent anywhere — useful for
      confirming the probes themselves work on a given machine.
    - **Set** (the real Arena DaemonSet's mode): every tick feeds an
      Aggregator; each time a window closes, the summary is run through
      StateEncoder and handed to a Publisher, which sends it to the
      Referee's /ingest endpoint (retrying on the next window if the
      Referee is briefly unreachable — see pipeline/publisher.py).
    """
    parser = argparse.ArgumentParser(description="Run the Panopticon Observer standalone")
    parser.add_argument("--process-name", default=os.environ.get("TARGET_PROCESS_NAME", "target-app"))
    parser.add_argument("--metrics-url", default=os.environ.get("TARGET_METRICS_URL"))
    parser.add_argument("--publish-url", default=os.environ.get("REFEREE_PUBLISH_URL"),
                        help="If set, aggregate+encode+publish to this URL instead of printing raw ticks")
    parser.add_argument("--window-seconds", type=float, default=float(os.environ.get("OBSERVER_WINDOW_SECONDS", "1.0")),
                        help="Aggregation window size when --publish-url is set")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--iterations", type=int, default=None, help="Stop after N ticks (omit to run forever)")
    args = parser.parse_args()

    observer = Observer(args.process_name, metrics_url=args.metrics_url)
    print(f"observer: watching '{args.process_name}' as pid {observer.process_probe.pid} "
          f"(syscall backend: {observer.syscall_probe.backend})")

    if args.publish_url:
        aggregator = Aggregator(window_seconds=args.window_seconds)
        encoder = StateEncoder()
        publisher = Publisher(args.publish_url)
        print(f"observer: publishing to {args.publish_url} (window={args.window_seconds}s, {encoder.size} fields)")

        def handle_event(event: dict):
            summary = aggregator.add(event)
            if summary:
                vector = encoder.encode(summary)
                ok = publisher.publish(vector, encoder.field_names())
                if not ok:
                    print(f"observer: publish failed, {publisher.queue_depth} event(s) queued for retry")
    else:
        print("observer: no --publish-url / REFEREE_PUBLISH_URL set — printing raw ticks only (local/dev mode)")

        def handle_event(event: dict):
            print(event)

    try:
        observer.run(args.interval, handle_event, iterations=args.iterations)
    except KeyboardInterrupt:
        pass
    finally:
        observer.close()


if __name__ == "__main__":
    main()
