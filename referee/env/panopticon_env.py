"""The multi-agent environment train.py steps through.

Two modes:

* ``mode="sim"`` (default) — fully self-contained. An internal
  ``ArenaSimulation`` models attack/defense pressure as a small set of
  continuous state variables and produces synthetic telemetry shaped
  exactly like what observer/pipeline/aggregator.py would hand to the
  encoder. This is what train.py actually learns against: it's fast,
  deterministic-with-a-seed, and needs nothing running anywhere else. It's
  also the same abstracted-effects approach used by published MARL
  cyber-defense environments (e.g. CSIRO's CybORG, the CAGE Challenges)
  rather than executing live exploits against a real service.

* ``mode="live"`` — delegates action application to action_executor.py,
  which makes real calls to the Red/Blue laptops, and reads observations
  from whatever Observer most recently published. Blue's actions are real
  in this mode (it really calls the Kubernetes API). Red's actions are
  still routed through the simulated attack engine in red-team/attacks/ —
  see that module's docstring for why.

Both modes produce observations through the *same* encoder
(observer/pipeline/state_encoder.py), so a policy trained in sim mode reads
the exact same vector shape it would see live.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from observation_builder import ObservationBuilder

_REFEREE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_REFEREE_ROOT)
sys.path.insert(0, _REFEREE_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "common"))
sys.path.insert(0, os.path.join(_REPO_ROOT, "red-team"))

from rewards.blue_reward import compute_blue_reward
from rewards.red_reward import compute_red_reward
from action_spaces import RED_ACTIONS, BLUE_ACTIONS, RED_NOOP_INDEX, BLUE_NOOP_INDEX
from target_types import DEVICE_SUSCEPTIBILITY
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

_RED_SIMULATORS = {
    "connection_pressure":  SlowlorisSimulator(),
    "cpu_pressure":         HashFloodSimulator(),
    "memory_pressure":      JsonBombSimulator(),
    "parsing_pressure":     DesyncSimulator(),
    "credential_stuffing":  CredentialStuffingSimulator(),
    "firmware_exploit":     FirmwareExploitSimulator(),
    "stream_hijack":        StreamHijackSimulator(),
    "adb_exploit":          AdbExploitSimulator(),
    "smb_relay":            SmbRelaySimulator(),
    "privilege_escalation": PrivilegeEscalationSimulator(),
    "dns_poisoning":        DnsPoisoningSimulator(),
    "arp_spoof":            ArpSpoofSimulator(),
    "deauth_flood":         DeauthFloodSimulator(),
    "lateral_movement":     LateralMovementSimulator(),
}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


class ArenaSimulation:
    """A small abstracted model of "how much trouble is the target-app in,"
    not a network stack. Each pressure variable stands in for the *effect*
    a real attack class would have, not the attack itself."""

    def __init__(self, seed: Optional[int] = None, device_type: str = "go_app"):
        self.rng = np.random.default_rng(seed)
        self.device_type = device_type
        self.pressures = {"connection": 0.0, "cpu": 0.0, "memory": 0.0, "parsing": 0.0}
        self.detection_confidence = 0.0
        self.baseline_requests = 200.0

    def apply_red(self, action: str) -> float:
        mag = 0.0
        susceptibility = DEVICE_SUSCEPTIBILITY.get(self.device_type, {}).get(action, 0.0)
        if action in _RED_SIMULATORS and susceptibility > 0.0:
            raw = _RED_SIMULATORS[action].step(self.rng)
            for k, v in raw.items():
                scaled = v * susceptibility
                self.pressures[k] = self.pressures.get(k, 0.0) + scaled
                mag = max(mag, scaled)
        elif action == "llm_generated" and susceptibility > 0.0:
            key = self.rng.choice(list(self.pressures.keys()))
            mag = float(self.rng.uniform(0.20, 0.40)) * susceptibility
            self.pressures[key] += mag
        return mag

    def apply_blue(self, action: str) -> float:
        relief = 0.0
        if action == "rate_limit":
            self.pressures["connection"] *= 0.5
            self.pressures["cpu"] *= 0.6
            relief = 0.30
        elif action == "isolate_pod":
            for k in self.pressures:
                self.pressures[k] = 0.0
            relief = 1.0
        elif action == "honeypot_redirect":
            self.pressures["parsing"] *= 0.4
            self.pressures["connection"] *= 0.7
            relief = 0.25
        elif action == "raise_alert_threshold":
            self.detection_confidence = min(1.0, self.detection_confidence + 0.2)
            relief = 0.05
        return relief

    def step_dynamics(self) -> tuple[float, float]:
        for k in self.pressures:
            self.pressures[k] *= 0.85  # natural recovery each tick
        combined = _clip01(sum(self.pressures.values()) / 2.0)
        self.detection_confidence = 0.8 * self.detection_confidence + 0.2 * combined
        service_health = _clip01(1.0 - combined)
        return combined, service_health

    def to_raw_telemetry(self, combined: float, service_health: float) -> dict:
        n = lambda scale: float(self.rng.normal(0, scale))
        established = max(0.0, 20 + combined * 250 + n(5))
        close_wait = max(0.0, combined * 150 + n(10))
        syn_sent = max(0.0, self.pressures["connection"] * 120 + n(5))
        bytes_sent = max(0.0, 50_000 + self.pressures["cpu"] * 2_000_000 + n(10_000))
        bytes_recv = max(0.0, 50_000 + self.pressures["memory"] * 1_500_000 + n(10_000))
        rss = 80_000_000 + self.pressures["memory"] * 300_000_000
        rss_delta = self.pressures["memory"] * 20_000_000 - 2_000_000
        cpu_percent = _clip01(combined + 0.05) * 100
        syscalls = max(0.0, 500 + combined * 15_000 + n(200))
        requests_per_window = max(0.0, self.baseline_requests * service_health + n(10))
        error_rate = _clip01(1 - service_health)

        return {
            "network.total_connections": established + close_wait + syn_sent,
            "network.connections_by_state.ESTABLISHED": established,
            "network.connections_by_state.CLOSE_WAIT": close_wait,
            "network.connections_by_state.SYN_SENT": syn_sent,
            "network.bytes_sent_delta": bytes_sent,
            "network.bytes_recv_delta": bytes_recv,
            "memory.rss_bytes": rss,
            "memory.rss_delta_bytes": rss_delta,
            "process.alive": 1.0,
            "process.restart_detected": 0.0,
            "process.cpu_percent": cpu_percent,
            "syscall.syscalls_per_interval": syscalls,
            "http.requests_per_window": requests_per_window,
            "http.error_rate": error_rate,
        }


class PanopticonEnv(ParallelEnv):
    metadata = {"name": "panopticon_v1"}

    def __init__(self, mode: str = "sim", max_steps: int = 200, seed: Optional[int] = None,
                 action_executor=None, target_device_type: str = "go_app"):
        super().__init__()
        if mode not in ("sim", "live"):
            raise ValueError("mode must be 'sim' or 'live'")
        self.mode = mode
        self.max_steps = max_steps
        self.action_executor = action_executor
        self.target_device_type = target_device_type
        if mode == "live" and action_executor is None:
            raise ValueError("mode='live' requires an action_executor (see action_executor.py)")

        self.possible_agents = ["red", "blue"]
        self.agents = list(self.possible_agents)

        self.builder = ObservationBuilder()
        self._obs_size = {a: self.builder.size_for(a) for a in self.possible_agents}

        self.action_spaces = {
            "red": spaces.Discrete(len(RED_ACTIONS)),
            "blue": spaces.Discrete(len(BLUE_ACTIONS)),
        }
        self.observation_spaces = {
            a: spaces.Box(low=0.0, high=1.0, shape=(self._obs_size[a],), dtype=np.float32)
            for a in self.possible_agents
        }

        self._sim: Optional[ArenaSimulation] = None
        self._step_count = 0
        self._seed = seed

    def observation_space(self, agent):
        return self.observation_spaces[agent]

    def action_space(self, agent):
        return self.action_spaces[agent]

    def reset(self, seed=None, options=None):
        self.agents = list(self.possible_agents)
        self._step_count = 0
        if options and "target_device_type" in options:
            self.target_device_type = options["target_device_type"]
        self._sim = ArenaSimulation(
            seed=seed if seed is not None else self._seed,
            device_type=self.target_device_type,
        )
        raw = self._sim.to_raw_telemetry(0.0, 1.0)
        obs = {a: self.builder.build(a, raw) for a in self.agents}
        infos = {a: {"target_device_type": self.target_device_type} for a in self.agents}
        return obs, infos

    def step(self, actions: dict):
        if self.mode == "sim":
            raw, combined, service_health = self._step_sim(actions)
        else:
            raw, combined, service_health = self._step_live(actions)

        obs = {a: self.builder.build(a, raw) for a in self.agents}

        red_id = actions.get("red", 0)
        blue_id = actions.get("blue", 0)
        rewards = {
            "red": compute_red_reward(service_health, red_id, noop_id=RED_NOOP_INDEX),
            "blue": compute_blue_reward(service_health, blue_id, noop_id=BLUE_NOOP_INDEX, true_pressure=combined),
        }

        self._step_count += 1
        done = self._step_count >= self.max_steps
        terminations = {a: False for a in self.agents}
        truncations = {a: done for a in self.agents}
        detection_confidence = self._sim.detection_confidence if self.mode == "sim" else None
        infos = {
            a: {
                "combined_pressure": combined,
                "service_health": service_health,
                "detection_confidence": detection_confidence,
            }
            for a in self.agents
        }

        if done:
            self.agents = []

        return obs, rewards, terminations, truncations, infos

    def _step_sim(self, actions: dict):
        red_action = RED_ACTIONS[actions.get("red", 0)]
        blue_action = BLUE_ACTIONS[actions.get("blue", 0)]
        self._sim.apply_red(red_action)
        self._sim.apply_blue(blue_action)
        combined, service_health = self._sim.step_dynamics()
        raw = self._sim.to_raw_telemetry(combined, service_health)
        return raw, combined, service_health

    def _step_live(self, actions: dict):
        red_action = RED_ACTIONS[actions.get("red", 0)]
        blue_action = BLUE_ACTIONS[actions.get("blue", 0)]
        self.action_executor.apply_red(red_action)
        self.action_executor.apply_blue(blue_action)
        raw = self.action_executor.latest_observation()
        # Ground truth for blue_reward's false-positive term isn't directly
        # observable live; the executor estimates it from the same raw
        # telemetry as a proxy (see action_executor.py).
        combined = self.action_executor.estimate_pressure(raw)
        service_health = _clip01(1.0 - combined)
        return raw, combined, service_health
