"""Small, shared pieces of reward math so red_reward.py and blue_reward.py
don't quietly drift apart on how they clip/shape/decay things."""
from __future__ import annotations


def clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def ema(previous: float, new: float, alpha: float = 0.2) -> float:
    """Exponential moving average — used to smooth reward components so a
    single noisy tick doesn't whipsaw either agent's signal."""
    return alpha * new + (1 - alpha) * previous


def action_cost(action_id: int, noop_id: int, cost: float = 0.01) -> float:
    """A small, constant cost for taking any non-noop action. Tiny on
    purpose — just enough to discourage spamming actions with no effect,
    not enough to make inaction the dominant strategy."""
    return 0.0 if action_id == noop_id else cost


def false_positive_cost(action_id: int, noop_id: int, true_pressure: float, threshold: float = 0.25, cost: float = 0.15) -> float:
    """Penalizes Blue for intervening when there wasn't much actually wrong
    — without this, the easiest policy is "always isolate the pod," which
    technically maximizes uptime metrics while being a useless policy."""
    if action_id != noop_id and true_pressure < threshold:
        return cost
    return 0.0
