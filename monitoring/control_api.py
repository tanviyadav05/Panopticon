"""Safe command-plane API backing the Red / Blue / Referee dashboard.

The command laptop is intentionally a coordinator, not an attack engine:

* Red requests are forwarded only to the existing simulated Red service.
* Blue's two disruptive Kubernetes actions need both an operator confirmation
  and ``PANOPTICON_BLUE_LIVE_ARMED=1`` on the Command laptop.
* Referee rounds always use ``PanopticonEnv(mode="sim")``.  Calling remote
  policy endpoints during a referee policy-step requests decisions only; it
  never asks either remote service to apply an action.
* Local-LLM analysis is limited to a defensive summary of the simulated
  state and is proxied to the LLM laptop's ``/agent/run`` endpoint.

Set ``PANOPTICON_CONTROL_TOKEN`` to require the matching
``X-Panopticon-Token`` header on state-changing routes.  The dashboard has a
session-only field for this token; it is never persisted by the browser.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from typing import Any, Optional

import numpy as np
import requests
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO_ROOT, "common"))
from action_spaces import BLUE_ACTIONS, RED_ACTIONS, BLUE_NOOP_INDEX, RED_NOOP_INDEX  # noqa: E402

from telemetry_api import TelemetryEvent, _get_registry, store  # noqa: E402

_REFEREE_ROOT = os.path.join(_REPO_ROOT, "referee")
_RED_ROOT = os.path.join(_REPO_ROOT, "red-team")
for _path in (_REFEREE_ROOT, _RED_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)
from env.action_executor import ActionExecutor  # noqa: E402
from env.observation_builder import ObservationBuilder  # noqa: E402
from rewards.blue_reward import compute_blue_reward  # noqa: E402
from rewards.red_reward import compute_red_reward  # noqa: E402

router = APIRouter(prefix="/control", tags=["control"])
_DESTRUCTIVE_BLUE_ACTIONS = {"isolate_pod", "honeypot_redirect"}
_LIVE_RED_ACTIONS = {"cpu_pressure", "memory_pressure"}
_live_ingest: Optional[ActionExecutor] = None
_live_ingest_lock = threading.Lock()


def _endpoint(name: str, fallback: str) -> str:
    return os.environ.get(name, fallback).rstrip("/")


def _token_is_valid(token: Optional[str]) -> bool:
    configured = os.environ.get("PANOPTICON_CONTROL_TOKEN", "")
    return not configured or token == configured


def _require_token(token: Optional[str]) -> None:
    if not _token_is_valid(token):
        raise HTTPException(status_code=401, detail="invalid or missing control token")


def _request_json(method: str, url: str, *, payload: Optional[dict] = None, timeout: float = 1.5) -> dict:
    try:
        response = requests.request(method, url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"ok": True, "data": data}
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": str(exc), "endpoint": url}


class ActionRequest(BaseModel):
    action: str
    confirm_live: bool = False


class RefereeStepRequest(BaseModel):
    red_action: str = "noop"
    blue_action: str = "noop"


class LiveCycleRequest(BaseModel):
    red_action: str = "cpu_pressure"
    confirm_live: bool = False


class LLMAnalysisRequest(BaseModel):
    max_iterations: int = Field(default=2, ge=1, le=3)


def ensure_live_ingest() -> bool:
    """Start the Observer listener only when the Command operator enables it."""
    global _live_ingest
    if os.environ.get("PANOPTICON_LIVE_REFEREE_INGEST", "0") != "1":
        return False
    with _live_ingest_lock:
        if _live_ingest is None:
            _live_ingest = ActionExecutor(
                red_endpoint=_endpoint("PANOPTICON_RED_URL", "http://red-laptop:8081"),
                blue_endpoint=_endpoint("PANOPTICON_BLUE_URL", "http://blue-laptop:8082"),
                ingest_port=int(os.environ.get("PANOPTICON_LIVE_INGEST_PORT", "9600")),
            )
            _live_ingest.start_ingest_server()
    return True


class LiveReferee:
    """Score fresh, actual Observer samples from an armed bounded lab cycle."""

    def __init__(self):
        self._encoder = ObservationBuilder().encoder
        self._step = 0
        self._lock = threading.Lock()

    @staticmethod
    def _pressure(state: dict) -> float:
        # Values are normalized by the shared Observer StateEncoder. These are
        # actual target measurements, not the simulation pressure variables.
        # memory.rss_delta maps zero to 0.5 in the schema because its raw range
        # spans negative and positive deltas; convert only the positive half
        # back into a pressure signal.
        memory_delta = max(0.0, (float(state.get("memory.rss_delta", 0.5)) - 0.5) * 2.0)
        components = [
            float(state.get("process.cpu_percent", 0.0)),
            memory_delta,
            float(state.get("http.error_rate", 0.0)),
        ]
        if float(state.get("process.alive", 1.0)) < 0.5:
            return 1.0
        return max(0.0, min(1.0, sum(components) / len(components)))

    def current(self) -> Optional[dict]:
        if _live_ingest is None:
            return None
        state, field_names, timestamp = _live_ingest.latest_snapshot()
        if not state or not field_names or not timestamp:
            return None
        vector = np.asarray([state.get(name, 0.0) for name in self._encoder.field_names()], dtype=np.float32)
        pressure = self._pressure(state)
        return {
            "timestamp": timestamp,
            "decoded_fields": self._encoder.decode(vector),
            "combined_pressure": pressure,
            "service_health": max(0.0, min(1.0, 1.0 - pressure)),
            "detection_confidence": pressure,
        }

    def wait_for_newer(self, after_timestamp: float, timeout_seconds: float = 8.0) -> Optional[dict]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            observation = self.current()
            if observation and observation["timestamp"] > after_timestamp:
                return observation
            time.sleep(0.25)
        return None

    def event(self, observation: dict, red_action: str, blue_action: str) -> TelemetryEvent:
        with self._lock:
            step = self._step
            self._step += 1
        target_type, target_name, target_id = referee._active_target()
        red_id = RED_ACTIONS.index(red_action)
        blue_id = BLUE_ACTIONS.index(blue_action)
        return TelemetryEvent(
            timestamp=observation["timestamp"],
            step=step,
            combined_pressure=observation["combined_pressure"],
            service_health=observation["service_health"],
            detection_confidence=observation["detection_confidence"],
            red_action=red_action,
            blue_action=blue_action,
            red_reward=compute_red_reward(observation["service_health"], red_id, RED_NOOP_INDEX),
            blue_reward=compute_blue_reward(observation["service_health"], blue_id, BLUE_NOOP_INDEX, observation["combined_pressure"]),
            decoded_fields=observation["decoded_fields"],
            target_id=target_id,
            target_device_type=target_type,
            target_name=target_name,
        )

    def status(self) -> dict:
        observation = self.current()
        return {
            "ingest_armed": os.environ.get("PANOPTICON_LIVE_REFEREE_INGEST", "0") == "1",
            "cycle_armed": os.environ.get("PANOPTICON_LIVE_CYCLE_ARMED", "0") == "1",
            "observing": observation is not None,
            "last_observation_at": observation["timestamp"] if observation else None,
        }


class RefereeRuntime:
    """Small in-process simulated referee session for dashboard controls."""

    def __init__(self):
        self._lock = threading.RLock()
        self._env: Any = None
        self._obs: Optional[dict] = None
        self._step = 0
        self._target_type = "go_app"

    def _imports(self) -> Any:
        referee_root = os.path.join(_REPO_ROOT, "referee")
        red_root = os.path.join(_REPO_ROOT, "red-team")
        for path in (referee_root, red_root):
            if path not in sys.path:
                sys.path.insert(0, path)
        from env.panopticon_env import PanopticonEnv
        return PanopticonEnv

    def _active_target(self) -> tuple[str, str, str]:
        try:
            target = _get_registry().active
            if target:
                return target.device_type, target.name, target.to_dict()["id"]
        except Exception:
            pass
        return "go_app", "target-app", "go_app:target-app"

    def reset(self) -> dict:
        with self._lock:
            target_type, _, _ = self._active_target()
            env_cls = self._imports()
            self._env = env_cls(mode="sim", max_steps=500, seed=int(time.time()), target_device_type=target_type)
            self._obs, _ = self._env.reset()
            self._step = 0
            self._target_type = target_type
            return self.status()

    def status(self) -> dict:
        with self._lock:
            return {
                "ready": self._env is not None and self._obs is not None,
                "step": self._step,
                "target_device_type": self._target_type,
                "mode": "sim",
            }

    def observations(self) -> dict:
        with self._lock:
            if self._obs is None:
                self.reset()
            return {agent: vector.tolist() for agent, vector in self._obs.items()}

    def step(self, red_action: str, blue_action: str) -> dict:
        if red_action not in RED_ACTIONS or blue_action not in BLUE_ACTIONS:
            raise ValueError("unknown Red or Blue action")
        with self._lock:
            if self._env is None or self._obs is None:
                self.reset()
            actions = {"red": RED_ACTIONS.index(red_action), "blue": BLUE_ACTIONS.index(blue_action)}
            next_obs, rewards, terminations, truncations, infos = self._env.step(actions)
            info = infos.get("red") or infos.get("blue") or {}
            target_type, target_name, target_id = self._active_target()
            raw = self._env._sim.to_raw_telemetry(info.get("combined_pressure", 0.0), info.get("service_health", 1.0))
            vector = self._env.builder.encoder.encode(raw)
            event = TelemetryEvent(
                step=self._step,
                combined_pressure=info.get("combined_pressure", 0.0),
                service_health=info.get("service_health", 1.0),
                detection_confidence=info.get("detection_confidence", 0.0),
                red_action=red_action,
                blue_action=blue_action,
                red_reward=rewards.get("red", 0.0),
                blue_reward=rewards.get("blue", 0.0),
                decoded_fields=self._env.builder.encoder.decode(vector),
                target_id=target_id,
                target_device_type=target_type,
                target_name=target_name,
            )
            store.add(event)
            self._step += 1
            if not self._env.agents:
                self._obs, _ = self._env.reset()
            else:
                self._obs = next_obs
            return {
                "ok": True,
                "event": event.model_dump(),
                "rewards": rewards,
                "terminated": bool(any(terminations.values()) or any(truncations.values())),
                "referee": self.status(),
            }


class ControlLog:
    def __init__(self, maxlen: int = 100):
        self._items: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, actor: str, action: str, result: dict) -> dict:
        item = {"timestamp": time.time(), "actor": actor, "action": action, "ok": bool(result.get("ok", False)), "result": result}
        with self._lock:
            self._items.append(item)
        return item

    def recent(self, limit: int = 30) -> list[dict]:
        with self._lock:
            return list(self._items)[-limit:]


referee = RefereeRuntime()
live_referee = LiveReferee()
control_log = ControlLog()


@router.get("/status")
def status():
    red = _request_json("GET", f"{_endpoint('PANOPTICON_RED_URL', 'http://red-laptop:8081')}/health", timeout=0.5)
    blue = _request_json("GET", f"{_endpoint('PANOPTICON_BLUE_URL', 'http://blue-laptop:8082')}/health", timeout=0.5)
    llm = _request_json("GET", f"{_endpoint('LLM_GATEWAY_URL', 'http://llm-laptop:8090')}/health", timeout=0.5)
    arena = _request_json("GET", f"{_endpoint('PANOPTICON_ARENA_URL', 'http://arena-laptop:30080')}/health", timeout=0.5)
    return {
        "services": {"red": red, "blue": blue, "llm": llm, "arena": arena},
        "referee": referee.status(),
        "live_referee": live_referee.status(),
        "actions": {"red": RED_ACTIONS, "blue": BLUE_ACTIONS},
        "blue_live_armed": os.environ.get("PANOPTICON_BLUE_LIVE_ARMED", "0") == "1",
        "control_token_required": bool(os.environ.get("PANOPTICON_CONTROL_TOKEN")),
        "recent_controls": control_log.recent(),
    }


@router.post("/red/act")
def red_act(req: ActionRequest, x_panopticon_token: Optional[str] = Header(default=None)):
    _require_token(x_panopticon_token)
    if req.action not in RED_ACTIONS:
        raise HTTPException(status_code=422, detail="unknown simulated Red action")
    target_type, _, _ = referee._active_target()
    result = _request_json(
        "POST",
        f"{_endpoint('PANOPTICON_RED_URL', 'http://red-laptop:8081')}/act",
        payload={"action": req.action, "target_device_type": target_type},
    )
    control_log.add("red", req.action, result)
    return result


@router.post("/blue/act")
def blue_act(req: ActionRequest, x_panopticon_token: Optional[str] = Header(default=None)):
    _require_token(x_panopticon_token)
    if req.action not in BLUE_ACTIONS:
        raise HTTPException(status_code=422, detail="unknown Blue action")
    if req.action in _DESTRUCTIVE_BLUE_ACTIONS:
        if not req.confirm_live:
            raise HTTPException(status_code=409, detail="check the live-action confirmation before applying this containment action")
        if os.environ.get("PANOPTICON_BLUE_LIVE_ARMED", "0") != "1":
            raise HTTPException(status_code=409, detail="set PANOPTICON_BLUE_LIVE_ARMED=1 on the Command laptop to arm live Blue containment")
    result = _request_json(
        "POST",
        f"{_endpoint('PANOPTICON_BLUE_URL', 'http://blue-laptop:8082')}/act",
        payload={"action": req.action},
    )
    control_log.add("blue", req.action, result)
    return result


@router.post("/referee/reset")
def referee_reset(x_panopticon_token: Optional[str] = Header(default=None)):
    _require_token(x_panopticon_token)
    result = referee.reset()
    control_log.add("referee", "reset", {"ok": True, **result})
    return {"ok": True, **result}


@router.post("/referee/step")
def referee_step(req: RefereeStepRequest, x_panopticon_token: Optional[str] = Header(default=None)):
    _require_token(x_panopticon_token)
    try:
        result = referee.step(req.red_action, req.blue_action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    control_log.add("referee", f"{req.red_action} / {req.blue_action}", result)
    return result


@router.post("/referee/policy-step")
def referee_policy_step(x_panopticon_token: Optional[str] = Header(default=None)):
    """Let both remote agents decide, then advance the *local simulation*.

    This deliberately calls ``/decide`` rather than ``/act`` on the remote
    laptops.  The only applied action is the dashboard's in-process sim step.
    """
    _require_token(x_panopticon_token)
    observations = referee.observations()
    target_type = referee.status()["target_device_type"]
    red_decision = _request_json(
        "POST", f"{_endpoint('PANOPTICON_RED_URL', 'http://red-laptop:8081')}/decide",
        payload={"observation": observations["red"], "target_device_type": target_type},
    )
    blue_decision = _request_json(
        "POST", f"{_endpoint('PANOPTICON_BLUE_URL', 'http://blue-laptop:8082')}/decide",
        payload={"observation": observations["blue"]},
    )
    red_action = red_decision.get("action", "noop") if red_decision.get("ok", True) else "noop"
    blue_action = blue_decision.get("action", "noop") if blue_decision.get("ok", True) else "noop"
    result = referee.step(red_action if red_action in RED_ACTIONS else "noop", blue_action if blue_action in BLUE_ACTIONS else "noop")
    result["decisions"] = {"red": red_decision, "blue": blue_decision}
    control_log.add("referee", "remote policy step", result)
    return result


@router.post("/live/cycle")
def live_cycle(req: LiveCycleRequest, x_panopticon_token: Optional[str] = Header(default=None)):
    """Run one bounded, observed CPU or memory pressure-and-relief cycle.

    The dashboard must be armed, Red/Blue/target each have an independent
    local arm, and the target accepts only fixed-size/short-duration work.
    No request field may change a target URL, duration, size, or Blue action.
    """
    _require_token(x_panopticon_token)
    if not req.confirm_live:
        raise HTTPException(status_code=409, detail="confirm this is the dedicated isolated lab before running a live cycle")
    if req.red_action not in _LIVE_RED_ACTIONS:
        raise HTTPException(status_code=422, detail="live cycles permit only cpu_pressure or memory_pressure")
    if os.environ.get("PANOPTICON_LIVE_CYCLE_ARMED", "0") != "1":
        raise HTTPException(status_code=409, detail="set PANOPTICON_LIVE_CYCLE_ARMED=1 on the Command laptop")
    if not ensure_live_ingest():
        raise HTTPException(status_code=409, detail="set PANOPTICON_LIVE_REFEREE_INGEST=1 and restart the dashboard")

    baseline = live_referee.current()
    if baseline is None or time.time() - baseline["timestamp"] > 10:
        raise HTTPException(status_code=503, detail="no fresh Observer telemetry; verify the Arena Observer can publish to command-laptop:9600")

    red_result = _request_json(
        "POST",
        f"{_endpoint('PANOPTICON_RED_URL', 'http://red-laptop:8081')}/act",
        payload={"action": req.red_action, "target_device_type": "go_app"},
        timeout=3.0,
    )
    workload_result = red_result.get("live_lab_workload", {})
    if not workload_result.get("ok", False):
        raise HTTPException(status_code=502, detail={"message": "Red did not start the bounded target workload", "red": red_result})

    incident = live_referee.wait_for_newer(baseline["timestamp"])
    if incident is None:
        # The target has a fixed short expiry. Ask Blue for cleanup as an
        # additional fail-safe if telemetry is temporarily unavailable.
        _request_json("POST", f"{_endpoint('PANOPTICON_BLUE_URL', 'http://blue-laptop:8082')}/act", payload={"action": "rate_limit"})
        raise HTTPException(status_code=504, detail="Red started the bounded workload but no new Observer sample arrived in time")
    incident_event = live_referee.event(incident, req.red_action, "noop")
    store.add(incident_event)

    blue_result = _request_json(
        "POST",
        f"{_endpoint('PANOPTICON_BLUE_URL', 'http://blue-laptop:8082')}/act",
        payload={"action": "rate_limit"},
        timeout=3.0,
    )
    if not blue_result.get("ok", False):
        raise HTTPException(status_code=502, detail={"message": "Blue did not apply live workload relief", "blue": blue_result})

    recovery = live_referee.wait_for_newer(incident["timestamp"])
    if recovery is None:
        raise HTTPException(status_code=504, detail="Blue applied relief but no recovery telemetry arrived in time")
    recovery_event = live_referee.event(recovery, req.red_action, "rate_limit")
    store.add(recovery_event)

    result = {
        "ok": True,
        "mode": "live_bounded_lab_workload",
        "red": red_result,
        "blue": blue_result,
        "incident": incident_event.model_dump(),
        "recovery": recovery_event.model_dump(),
        "referee": live_referee.status(),
    }
    control_log.add("live-referee", f"{req.red_action} / rate_limit", result)
    return result


@router.post("/referee/local-llm-analysis")
def referee_local_llm_analysis(req: LLMAnalysisRequest, x_panopticon_token: Optional[str] = Header(default=None)):
    _require_token(x_panopticon_token)
    state = referee.status()
    latest = store.recent(1)
    latest_event = latest[0].model_dump() if latest else {}
    task = (
        "You are the referee for a closed, simulated defensive-security research range. "
        "Review the following abstract simulation state and reply in at most 100 words with one of: continue, pause, or reset, "
        "then give defensive-only reasons. Do not propose attack payloads, exploit steps, or real network actions.\n\n"
        f"Referee state: {state}\nLatest simulated event: {latest_event}"
    )
    result = _request_json(
        "POST",
        f"{_endpoint('LLM_GATEWAY_URL', 'http://llm-laptop:8090')}/agent/run",
        payload={"task": task, "target_context": {"mode": "sim", "role": "referee"}, "max_iterations": req.max_iterations},
        timeout=95.0,
    )
    control_log.add("referee", "local LLM analysis", result)
    return result


@router.get("/log")
def recent_log(limit: int = Query(default=30, ge=1, le=100)):
    return control_log.recent(limit)
