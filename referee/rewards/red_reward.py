"""Red is rewarded for service degradation, full stop — not for "using" any
particular attack module, which keeps the reward agnostic to whichever
concrete action set red-team/attacks/ ends up wired to.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reward_utils import action_cost, clip01


def compute_red_reward(service_health: float, action_id: int, noop_id: int) -> float:
    """service_health is in [0, 1] (1 = perfectly healthy). Red wants this
    low, so its reward is the degradation, minus a small per-action cost so
    it isn't free to spam actions that aren't accomplishing anything."""
    degradation = clip01(1.0 - service_health)
    return degradation - action_cost(action_id, noop_id)
