"""Telemetry store + REST API: event history, widget endpoints, and the
/targets family backed by arena.targets.target_registry."""
from __future__ import annotations
import os, sys, threading, time
from collections import deque
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_registry = None
_registry_lock = threading.Lock()

def _get_registry():
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                sys.path.insert(0, _repo)
                from arena.targets.target_registry import registry
                _registry = registry
    return _registry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from widgets import cpu_widget, network_widget, attack_timeline

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")))
from metrics import counter, gauge

TELEMETRY_EVENTS_TOTAL = counter("panopticon_telemetry_events_total", "Telemetry events ingested", ("target_device_type",))
SERVICE_HEALTH_GAUGE = gauge("panopticon_service_health", "Most recent service_health value")
COMBINED_PRESSURE_GAUGE = gauge("panopticon_combined_pressure", "Most recent combined_pressure value")


class TelemetryEvent(BaseModel):
    timestamp: Optional[float] = None
    step: int = 0
    combined_pressure: float = 0.0
    service_health: float = 1.0
    detection_confidence: float = 0.0
    red_action: str = "noop"
    blue_action: str = "noop"
    red_reward: float = 0.0
    blue_reward: float = 0.0
    decoded_fields: dict = {}
    target_id: str = "go_app:target-app"
    target_device_type: str = "go_app"
    target_name: str = "target-app"

    def model_post_init(self, __context) -> None:
        if self.timestamp is None:
            self.timestamp = time.time()


class TelemetryStore:
    def __init__(self, maxlen: int = 2000):
        self._lock = threading.Lock()
        self._events: deque = deque(maxlen=maxlen)
        self._cursor = 0

    def add(self, event: TelemetryEvent):
        with self._lock:
            self._events.append(event)
            self._cursor += 1

    def recent(self, limit: int = 200):
        with self._lock:
            return list(self._events)[-limit:]

    def since(self, cursor: int):
        with self._lock:
            missed = self._cursor - cursor
            if missed <= 0:
                return [], self._cursor
            take = min(missed, len(self._events))
            return list(self._events)[-take:], self._cursor


store = TelemetryStore()
router = APIRouter()


@router.post("/telemetry")
def ingest_telemetry(event: TelemetryEvent):
    store.add(event)
    TELEMETRY_EVENTS_TOTAL.labels(target_device_type=event.target_device_type).inc()
    SERVICE_HEALTH_GAUGE.set(event.service_health)
    COMBINED_PRESSURE_GAUGE.set(event.combined_pressure)
    return {"ok": True}

@router.get("/telemetry/recent")
def recent_telemetry(limit: int = 200):
    return [e.model_dump() for e in store.recent(limit)]

@router.get("/widgets/cpu")
def widget_cpu(limit: int = 60):
    return cpu_widget.shape(store.recent(limit))

@router.get("/widgets/network")
def widget_network(limit: int = 60):
    return network_widget.shape(store.recent(limit))

@router.get("/widgets/attack_timeline")
def widget_attack_timeline(limit: int = 60):
    return attack_timeline.shape(store.recent(limit))


@router.get("/targets")
def list_targets():
    return _get_registry().as_list()

@router.get("/targets/active")
def get_active_target():
    t = _get_registry().active
    return t.to_dict() if t else {}

class SelectRequest(BaseModel):
    device_id: str

@router.post("/targets/select")
def select_target(req: SelectRequest):
    ok = _get_registry().select(req.device_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"unknown device_id '{req.device_id}'")
    t = _get_registry().active
    return {"ok": True, "selected": t.to_dict() if t else {}}

@router.get("/targets/{device_type}/{device_name}/probe")
def probe_target(device_type: str, device_name: str):
    device_id = f"{device_type}:{device_name}"
    result = _get_registry().probe_one(device_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"unknown device_id '{device_id}'")
    return result

@router.get("/targets/{device_type}/{device_name}")
def get_target(device_type: str, device_name: str):
    t = _get_registry().get(f"{device_type}:{device_name}")
    if t is None:
        raise HTTPException(status_code=404, detail="not found")
    return t.to_dict()
