"""A small actor-critic network shared by the training loop
(referee/training/) and the lightweight edge-inference wrappers
(red-team/strategies/attack_policy.py, blue-team/countermeasures/
blue_controller.py). One definition, so a checkpoint trained centrally
always loads back into the exact same architecture wherever it's deployed.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torch.distributions import Categorical


class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int, n_actions: int, hidden_size: int = 64):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(obs_dim, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
        )
        self.policy_head = nn.Linear(hidden_size, n_actions)
        self.value_head = nn.Linear(hidden_size, 1)

    def forward(self, obs: torch.Tensor):
        h = self.shared(obs)
        logits = self.policy_head(h)
        value = self.value_head(h).squeeze(-1)
        return logits, value

    def act(self, obs: torch.Tensor):
        """Sample an action; returns (action, log_prob, value, entropy)."""
        logits, value = self.forward(obs)
        dist = Categorical(logits=logits)
        action = dist.sample()
        return action, dist.log_prob(action), value, dist.entropy()

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor):
        """Used during the PPO update: re-evaluate log_prob/entropy/value
        for previously-collected (obs, action) pairs under the *current*
        (post-update-in-progress) policy."""
        logits, value = self.forward(obs)
        dist = Categorical(logits=logits)
        return dist.log_prob(actions), value, dist.entropy()
