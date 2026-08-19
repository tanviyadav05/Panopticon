"""Red's top-level controller — 14 attack classes plus LLM-generated."""
from __future__ import annotations
import os, sys, time
import numpy as np, uvicorn
import requests
from fastapi import FastAPI
from pydantic import BaseModel

_THIS  = os.path.dirname(os.path.abspath(__file__))
_RED   = os.path.dirname(_THIS)
_REPO  = os.path.dirname(_RED)
sys.path.insert(0, _RED)
sys.path.insert(0, os.path.join(_REPO, "common"))

from metrics import mount_metrics, counter, histogram

RED_ACTIONS_TOTAL = counter("panopticon_red_actions_total", "Red attack actions executed", ("action", "target_device_type"))
RED_ACTION_LATENCY = histogram("panopticon_red_action_latency_seconds", "Red action execution latency")

from attacks.slowloris            import SlowlorisSimulator
from attacks.hash_flood           import HashFloodSimulator
from attacks.json_bomb            import JsonBombSimulator
from attacks.tcp_desync           import DesyncSimulator
from attacks.credential_stuffing  import CredentialStuffingSimulator
from attacks.firmware_exploit     import FirmwareExploitSimulator
from attacks.stream_hijack        import StreamHijackSimulator
from attacks.adb_exploit          import AdbExploitSimulator
from attacks.smb_relay            import SmbRelaySimulator
from attacks.privilege_escalation import PrivilegeEscalationSimulator
from attacks.dns_poisoning        import DnsPoisoningSimulator
from attacks.arp_spoof            import ArpSpoofSimulator
from attacks.deauth_flood         import DeauthFloodSimulator
from attacks.lateral_movement     import LateralMovementSimulator
from generators.llm_payload_generator import LLMPayloadGenerator
from strategies.attack_policy    import AttackPolicy
from action_spaces import RED_ACTIONS

_SIMULATORS = {
    "connection_pressure": SlowlorisSimulator(),
    "cpu_pressure": HashFloodSimulator(),
    "memory_pressure": JsonBombSimulator(),
    "parsing_pressure": DesyncSimulator(),
    "credential_stuffing": CredentialStuffingSimulator(),
    "firmware_exploit": FirmwareExploitSimulator(),
    "stream_hijack": StreamHijackSimulator(),
    "adb_exploit": AdbExploitSimulator(),
    "smb_relay": SmbRelaySimulator(),
    "privilege_escalation": PrivilegeEscalationSimulator(),
    "dns_poisoning": DnsPoisoningSimulator(),
    "arp_spoof": ArpSpoofSimulator(),
    "deauth_flood": DeauthFloodSimulator(),
    "lateral_movement": LateralMovementSimulator(),
}


class RedAttacker:
    def __init__(self, checkpoint_path=None):
        self.policy = AttackPolicy(checkpoint_path)
        self.llm    = LLMPayloadGenerator()
        self.rng    = np.random.default_rng()
        self._ctx   = {"recent_actions": [], "target_device_type": "go_app"}

    def set_target(self, device_type: str):
        self._ctx["target_device_type"] = device_type

    @staticmethod
    def _live_workloads_enabled() -> bool:
        """The opt-in path can only contact the fixed Arena control API.

        It starts a bounded in-pod workload in the isolated lab; it does not
        emit network traffic or accept a caller-supplied destination.
        """
        return os.environ.get("RED_LIVE_WORKLOADS_ARMED", "0") == "1"

    def _trigger_live_workload(self, action_name: str) -> dict:
        target_url = os.environ.get("PANOPTICON_LAB_TARGET_URL", "").rstrip("/")
        token = os.environ.get("PANOPTICON_LAB_CONTROL_TOKEN", "")
        if not target_url or not token:
            return {"ok": False, "reason": "PANOPTICON_LAB_TARGET_URL and PANOPTICON_LAB_CONTROL_TOKEN must be configured"}
        endpoint = "/api/lab/workload/cpu" if action_name == "cpu_pressure" else "/api/lab/workload/memory"
        try:
            response = requests.post(f"{target_url}{endpoint}", headers={"X-Panopticon-Lab-Token": token}, timeout=2.0)
            payload = response.json()
            return {"ok": response.ok, "endpoint": endpoint, "result": payload}
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "endpoint": endpoint, "reason": str(exc)}

    def execute(self, action_name: str) -> dict:
        start = time.monotonic()
        if action_name == "noop":
            effect = {}
        elif action_name == "llm_generated":
            effect = self.llm.propose(self._ctx, self.rng)
        elif action_name in _SIMULATORS:
            effect = _SIMULATORS[action_name].step(self.rng)
        else:
            return {"ok": False, "error": f"unknown action '{action_name}'"}
        self._ctx["recent_actions"] = (self._ctx["recent_actions"] + [action_name])[-10:]
        RED_ACTIONS_TOTAL.labels(action=action_name, target_device_type=self._ctx.get("target_device_type", "go_app")).inc()
        RED_ACTION_LATENCY.observe(time.monotonic() - start)
        result = {"ok": True, "action": action_name, "synthetic_effect": effect, "timestamp": time.time()}
        if action_name in {"cpu_pressure", "memory_pressure"} and self._live_workloads_enabled():
            result["live_lab_workload"] = self._trigger_live_workload(action_name)
        return result

    def decide(self, observation):
        vector = np.asarray(observation, dtype=np.float32).reshape(-1)
        if vector.size != 7:
            raise ValueError(f"expected 7 Red-visible telemetry values, got {vector.size}")
        return self.policy.decide(vector)

    def autonomous_tick(self, observation, target_device_type: str) -> dict:
        """Choose and execute one simulated action from the local policy."""
        self.set_target(target_device_type)
        action = self.decide(observation)
        result = self.execute(action)
        return {**result, "decision_source": "policy", "autonomous": True}


class ActRequest(BaseModel):
    action: str; target_device_type: str = "go_app"
class DecideRequest(BaseModel):
    observation: list; target_device_type: str = "go_app"
class TargetRequest(BaseModel):
    device_type: str
class AutonomyRequest(BaseModel):
    observation: list
    target_device_type: str = "go_app"


def build_app(checkpoint_path=None):
    attacker = RedAttacker(checkpoint_path)
    app = FastAPI(title="Panopticon Red Attacker")

    @app.post("/act")
    def act(req: ActRequest):
        attacker.set_target(req.target_device_type)
        return attacker.execute(req.action)

    @app.post("/decide")
    def decide(req: DecideRequest):
        attacker.set_target(req.target_device_type)
        try:
            return {"action": attacker.decide(req.observation)}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/autonomy/tick")
    def autonomy_tick(req: AutonomyRequest):
        try:
            return attacker.autonomous_tick(req.observation, req.target_device_type)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/set-target")
    def set_target(req: TargetRequest):
        attacker.set_target(req.device_type)
        return {"ok": True, "target_device_type": req.device_type}

    @app.get("/attacks")
    def list_attacks():
        return {"all_attacks": RED_ACTIONS, "count": len(RED_ACTIONS)}

    @app.get("/health")
    def health():
        return {"status": "ok", "role": "red-attacker",
                "current_target": attacker._ctx.get("target_device_type"),
                "live_lab_workloads_armed": attacker._live_workloads_enabled(),
                "lab_target_configured": bool(os.environ.get("PANOPTICON_LAB_TARGET_URL"))}

    mount_metrics(app)
    return app


if __name__ == "__main__":
    app = build_app(checkpoint_path=os.environ.get("RED_CHECKPOINT_PATH"))
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT","8081")))
