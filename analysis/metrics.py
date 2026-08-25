"""Shared metric definitions — used by referee/training/evaluate.py and by
plot_results.py / compare_agents.py, so "win rate" means the same thing
everywhere instead of being recomputed slightly differently in three places.

All functions take a list of "episode logs": each one a dict with at least
    {"service_health": [..per-step..], "combined_pressure": [..per-step..],
     "detection_confidence": [..per-step..], "red_return": float, "blue_return": float}
as produced by referee/training/evaluate.py's rollout loop.
"""
from __future__ import annotations

import numpy as np


def win_rate(episode_logs: list[dict], health_threshold: float = 0.5) -> float:
    """Blue "wins" an episode if mean service_health over the episode stays
    at or above the threshold; otherwise Red wins. Returns Blue's win rate.
    """
    if not episode_logs:
        return float("nan")
    wins = sum(1 for ep in episode_logs if np.mean(ep["service_health"]) >= health_threshold)
    return wins / len(episode_logs)


def mean_time_to_detect(episode_logs: list[dict], confidence_threshold: float = 0.5) -> float:
    """Average number of steps until detection_confidence first crosses the
    threshold. Episodes where it never crosses are counted at full episode
    length (a conservative "never detected in time" penalty rather than
    being excluded outright)."""
    times = []
    for ep in episode_logs:
        confidences = ep.get("detection_confidence") or []
        crossed = next((i for i, c in enumerate(confidences) if c is not None and c >= confidence_threshold), None)
        times.append(crossed if crossed is not None else len(confidences))
    return float(np.mean(times)) if times else float("nan")


def mean_time_to_exploit(episode_logs: list[dict], pressure_threshold: float = 0.5) -> float:
    """Average number of steps until combined_pressure first crosses the
    threshold — Red's mirror of mean_time_to_detect."""
    times = []
    for ep in episode_logs:
        pressures = ep.get("combined_pressure") or []
        crossed = next((i for i, p in enumerate(pressures) if p >= pressure_threshold), None)
        times.append(crossed if crossed is not None else len(pressures))
    return float(np.mean(times)) if times else float("nan")


def summarize(episode_logs: list[dict]) -> dict:
    return {
        "episodes": len(episode_logs),
        "blue_win_rate": win_rate(episode_logs),
        "mean_time_to_detect": mean_time_to_detect(episode_logs),
        "mean_time_to_exploit": mean_time_to_exploit(episode_logs),
        "mean_red_return": float(np.mean([ep["red_return"] for ep in episode_logs])) if episode_logs else float("nan"),
        "mean_blue_return": float(np.mean([ep["blue_return"] for ep in episode_logs])) if episode_logs else float("nan"),
        "mean_service_health": float(np.mean([np.mean(ep["service_health"]) for ep in episode_logs])) if episode_logs else float("nan"),
    }
