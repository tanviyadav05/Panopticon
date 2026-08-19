"""Wraps the trained Red policy (or a hand-coded heuristic baseline before
one exists) so red_attacker.py can decide "what do I do this step" using
only a local observation — no round-trip to the Referee needed once a
checkpoint has been trained and copied to this laptop.

The network architecture comes from common/policy_network.py (the same
class referee/training/train.py trains), so a checkpoint produced centrally
loads here without modification.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import torch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))  # red-team/strategies -> red-team -> repo root
sys.path.insert(0, os.path.join(_REPO_ROOT, "common"))

from policy_network import ActorCritic  # noqa: E402
from action_spaces import RED_ACTIONS  # noqa: E402


class AttackPolicy:
    def __init__(self, checkpoint_path: str | None = None, obs_dim: int = 7, hidden_size: int = 64):
        self.obs_dim = obs_dim
        self.model: ActorCritic | None = None
        if checkpoint_path and os.path.exists(checkpoint_path):
            self.load(checkpoint_path)
        else:
            self._rng = np.random.default_rng()

    def load(self, checkpoint_path: str):
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        red_payload = payload["red"]
        model = ActorCritic(red_payload["obs_dim"], red_payload["n_actions"], red_payload["hidden_size"])
        model.load_state_dict(red_payload["model"])
        model.eval()
        self.model = model

    def decide(self, observation: np.ndarray, deterministic: bool = True) -> str:
        """observation must already be in the 7-field Red-visible shape
        that referee/env/observation_builder.py produces. Returns an action
        *name* from common/action_spaces.RED_ACTIONS, not an index — that
        way red_attacker.py never has to know the index<->name mapping."""
        if self.model is None:
            return self._heuristic(observation)

        with torch.no_grad():
            logits, _ = self.model.forward(torch.as_tensor(observation, dtype=torch.float32).unsqueeze(0))
            if deterministic:
                idx = int(torch.argmax(logits, dim=-1).item())
            else:
                idx = int(torch.distributions.Categorical(logits=logits).sample().item())
        return RED_ACTIONS[idx]

    def _heuristic(self, observation: np.ndarray) -> str:
        """Before any checkpoint exists: lean on whichever pressure the
        target currently looks least defended against, with some
        randomness so it doesn't immediately become predictable."""
        # observation layout matches RED_VISIBLE_FIELDS in observation_builder.py:
        # [total_connections, established, close_wait, syn_sent, bytes_sent_rate, bytes_recv_rate, error_rate]
        if self._rng.random() < 0.15:
            return "noop"
        if self._rng.random() < 0.10:
            return "llm_generated"
        connection_signal = float(observation[2]) if len(observation) > 2 else 0.0  # close_wait
        cpu_signal = float(observation[4]) if len(observation) > 4 else 0.0          # bytes_sent_rate proxy
        if connection_signal < 0.3:
            return "connection_pressure"
        if cpu_signal < 0.3:
            return "cpu_pressure"
        return self._rng.choice(["memory_pressure", "parsing_pressure"])
