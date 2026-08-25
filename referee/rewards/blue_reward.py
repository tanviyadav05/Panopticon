"""Blue is rewarded for service health, but the naive version of that reward
("always isolate everything") is a degenerate policy, so the false-positive
penalty in reward_utils matters as much as the health term itself.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reward_utils import action_cost, clip01, false_positive_cost


def compute_blue_reward(service_health: float, action_id: int, noop_id: int, true_pressure: float) -> float:
    """service_health and true_pressure are both in [0, 1]. true_pressure is
    the (Blue doesn't directly observe this — it's ground truth used only
    for reward calculation, the same way a CTF's scoring server knows things
    the players don't) actual combined attack pressure this tick, used only
    to penalize swinging the isolate-everything hammer when nothing's wrong.
    """
    health_term = clip01(service_health)
    fp_penalty = false_positive_cost(action_id, noop_id, true_pressure)
    return health_term - fp_penalty - action_cost(action_id, noop_id, cost=0.005)
