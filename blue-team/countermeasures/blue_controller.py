"""Blue's top-level controller — the live-mode counterpart to sim mode's
ArenaSimulation.apply_blue() in referee/env/panopticon_env.py, and the
mirror of red-team/attacks/red_attacker.py. Unlike Red's actions, every
countermeasure dispatched from here is real: it calls the actual
Kubernetes API against the actual Arena.

Serves:
  POST /act     {"action": "<name>"}      -> applies that countermeasure for real
  POST /decide  {"observation": [floats]} -> returns what Blue's own policy
                                              (or, before training, the
                                              anomaly-detector heuristic)
                                              would choose
  POST /advise  {"observation": [floats]} -> asks the *local* LLM for a
                                              bounded recommendation only
  POST /autonomy/tick -> decides and, only when explicitly enabled, applies
                          a countermeasure

The autonomous endpoint is deliberately dry-run by default.  Set
``BLUE_AUTONOMY_APPLY=1`` on the Blue laptop before requests with
``apply=true`` are allowed.  This keeps a dashboard click or an LLM outage
from silently changing the Arena.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import torch
import uvicorn
import requests
from fastapi import FastAPI
from pydantic import BaseModel

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BLUE_TEAM_ROOT = os.path.dirname(_THIS_DIR)
_REPO_ROOT = os.path.dirname(_BLUE_TEAM_ROOT)
sys.path.insert(0, _BLUE_TEAM_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "common"))

from action_spaces import BLUE_ACTIONS  # noqa: E402
from policy_network import ActorCritic  # noqa: E402
from countermeasures.anomaly_detector import AnomalyDetector  # noqa: E402
from countermeasures.rate_limiter import PerKeyRateLimiter  # noqa: E402
from countermeasures.pod_isolator import PodIsolator  # noqa: E402
from countermeasures.honeypot_redirect import HoneypotRedirect  # noqa: E402
from generators.llm_defense_advisor import LLMDefenseAdvisor  # noqa: E402
from metrics import mount_metrics, counter, histogram  # noqa: E402

BLUE_ACTIONS_TOTAL = counter("panopticon_blue_actions_total", "Blue countermeasures executed", ("action", "ok"))
BLUE_ACTION_LATENCY = histogram("panopticon_blue_action_latency_seconds", "Blue action execution latency")
BLUE_ANOMALY_SCORE = histogram("panopticon_blue_anomaly_score", "Anomaly scores seen by the heuristic policy", buckets=(0.0, 0.2, 0.4, 0.45, 0.6, 0.75, 0.9, 1.0))
_LIVE_ACTIONS = {"isolate_pod", "honeypot_redirect"}


class BluePolicy:
    """Loads a trained Blue checkpoint if one's available; otherwise falls
    back to acting directly on the anomaly detector's score, so
    blue_controller is useful from the very first run, before anything has
    been trained."""

    def __init__(self, checkpoint_path: str | None, detector: AnomalyDetector):
        self.detector = detector
        self.model: ActorCritic | None = None
        if checkpoint_path and os.path.exists(checkpoint_path):
            self.load(checkpoint_path)

    def load(self, checkpoint_path: str):
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        blue_payload = payload["blue"]
        model = ActorCritic(blue_payload["obs_dim"], blue_payload["n_actions"], blue_payload["hidden_size"])
        model.load_state_dict(blue_payload["model"])
        model.eval()
        self.model = model

    def decide(self, observation: np.ndarray, deterministic: bool = True) -> str:
        if self.model is not None:
            with torch.no_grad():
                logits, _ = self.model.forward(torch.as_tensor(observation, dtype=torch.float32).unsqueeze(0))
                idx = int(torch.argmax(logits, dim=-1).item()) if deterministic else int(
                    torch.distributions.Categorical(logits=logits).sample().item()
                )
            return BLUE_ACTIONS[idx]
        return self._heuristic(observation)

    def _heuristic(self, observation: np.ndarray) -> str:
        score = self.detector.anomaly_score(observation)
        if score < 0.45:
            return "noop"
        if score < 0.6:
            return "rate_limit"
        if score < 0.75:
            return "honeypot_redirect"
        return "isolate_pod"


class BlueController:
    def __init__(self, checkpoint_path: str | None = None):
        self.detector = AnomalyDetector()
        self.policy = BluePolicy(checkpoint_path, self.detector)
        self.rate_limiter = PerKeyRateLimiter(capacity=20, refill_rate=5)
        self.isolator = PodIsolator()
        self.honeypot = HoneypotRedirect()
        self.advisor = LLMDefenseAdvisor()

    @staticmethod
    def _live_workload_relief_enabled() -> bool:
        return os.environ.get("BLUE_LIVE_WORKLOAD_RELIEF_ARMED", "0") == "1"

    def _stop_live_lab_workload(self) -> dict:
        """Stop the fixed Arena workload only when a Blue operator arms it."""
        target_url = os.environ.get("PANOPTICON_LAB_TARGET_URL", "").rstrip("/")
        token = os.environ.get("PANOPTICON_LAB_CONTROL_TOKEN", "")
        if not target_url or not token:
            return {"ok": False, "reason": "PANOPTICON_LAB_TARGET_URL and PANOPTICON_LAB_CONTROL_TOKEN must be configured"}
        try:
            response = requests.post(
                f"{target_url}/api/lab/workload/stop",
                headers={"X-Panopticon-Lab-Token": token},
                timeout=2.0,
            )
            payload = response.json()
            return {"ok": response.ok, "result": payload}
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "reason": str(exc)}

    def execute(self, action_name: str) -> dict:
        start = time.monotonic()
        result = self._execute(action_name)
        BLUE_ACTIONS_TOTAL.labels(action=action_name, ok=str(result.get("ok", False))).inc()
        BLUE_ACTION_LATENCY.observe(time.monotonic() - start)
        return result

    def _execute(self, action_name: str) -> dict:
        if action_name == "noop":
            return {"ok": True, "action": "noop"}
        if action_name == "rate_limit":
            self.rate_limiter.tighten(0.5)
            result = {"ok": True, "action": "rate_limit", "new_capacity": self.rate_limiter.capacity}
            if self._live_workload_relief_enabled():
                result["live_lab_workload_relief"] = self._stop_live_lab_workload()
                result["ok"] = bool(result["live_lab_workload_relief"].get("ok", False))
            return result
        if action_name in _LIVE_ACTIONS and os.environ.get("BLUE_LIVE_ACTIONS_ARMED", "0") != "1":
            return {
                "ok": False,
                "action": action_name,
                "reason": "live containment is disarmed; set BLUE_LIVE_ACTIONS_ARMED=1 on the Blue laptop",
            }
        if action_name == "isolate_pod":
            result = self.isolator.isolate({"app": "target-app"}, "target-app")
            return {"ok": result["ok"], "action": "isolate_pod", **result}
        if action_name == "honeypot_redirect":
            result = self.honeypot.enable()
            return {"ok": result["ok"], "action": "honeypot_redirect", **result}
        if action_name == "raise_alert_threshold":
            return {"ok": True, "action": "raise_alert_threshold"}
        return {"ok": False, "error": f"unknown action '{action_name}'"}

    def decide(self, observation: list[float]) -> str:
        vector = self._validate_observation(observation)
        score = self.detector.anomaly_score(vector)
        BLUE_ANOMALY_SCORE.observe(score)
        return self.policy.decide(vector)

    def advise(self, observation: list[float]) -> dict:
        """Return a constrained local-LLM proposal without applying it."""
        return self.advisor.propose(self._validate_observation(observation))

    def autonomous_tick(self, observation: list[float], use_llm: bool = False, apply: bool = False) -> dict:
        """One autonomous decision cycle.

        LLM advice is optional and can only name a member of BLUE_ACTIONS.
        Applying any chosen countermeasure remains an explicit, opt-in
        deployment decision on the Blue laptop.
        """
        vector = self._validate_observation(observation)
        proposal = self.advisor.propose(vector) if use_llm else None
        action = proposal["action"] if proposal else self.decide(vector.tolist())
        result = {
            "ok": True,
            "action": action,
            "applied": False,
            "decision_source": proposal.get("source", "policy") if proposal else "policy",
        }
        if proposal:
            result["advice"] = proposal
        if not apply:
            return result
        if os.environ.get("BLUE_AUTONOMY_APPLY", "0") != "1":
            return {
                **result,
                "ok": False,
                "error": "autonomous application is disabled; set BLUE_AUTONOMY_APPLY=1 on the Blue laptop",
            }
        executed = self.execute(action)
        return {**executed, "applied": bool(executed.get("ok")), "decision_source": result["decision_source"], **({"advice": proposal} if proposal else {})}

    def _validate_observation(self, observation: list[float]) -> np.ndarray:
        vector = np.asarray(observation, dtype=np.float32).reshape(-1)
        if vector.size != self.detector.n_features:
            raise ValueError(f"expected {self.detector.n_features} Blue telemetry values, got {vector.size}")
        return vector


class ActRequest(BaseModel):
    action: str


class DecideRequest(BaseModel):
    observation: list[float]


class AutonomyRequest(BaseModel):
    observation: list[float]
    use_llm: bool = False
    apply: bool = False


def build_app(checkpoint_path: str | None = None) -> FastAPI:
    controller = BlueController(checkpoint_path)
    app = FastAPI(title="Panopticon Blue Controller")

    @app.post("/act")
    def act(req: ActRequest):
        return controller.execute(req.action)

    @app.post("/decide")
    def decide(req: DecideRequest):
        try:
            return {"action": controller.decide(req.observation)}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/advise")
    def advise(req: DecideRequest):
        try:
            return controller.advise(req.observation)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/autonomy/tick")
    def autonomy_tick(req: AutonomyRequest):
        try:
            return controller.autonomous_tick(req.observation, use_llm=req.use_llm, apply=req.apply)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "role": "blue-controller",
            "cluster_available": controller.isolator.available,
            "local_llm_advisor": controller.advisor.llm_gateway_url,
            "live_actions_armed": os.environ.get("BLUE_LIVE_ACTIONS_ARMED", "0") == "1",
            "autonomous_apply_enabled": os.environ.get("BLUE_AUTONOMY_APPLY", "0") == "1",
            "live_workload_relief_armed": controller._live_workload_relief_enabled(),
            "lab_target_configured": bool(os.environ.get("PANOPTICON_LAB_TARGET_URL")),
        }

    mount_metrics(app)
    return app


if __name__ == "__main__":
    app = build_app(checkpoint_path=os.environ.get("BLUE_CHECKPOINT_PATH"))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8082")))
