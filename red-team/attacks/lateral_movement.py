"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class LateralMovementSimulator:
    name = "lateral_movement"
    description = "Post-compromise lateral movement class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'connection': float(rng.uniform(0.10,0.20)), 'cpu': float(rng.uniform(0.05,0.15)), 'memory': float(rng.uniform(0.05,0.15))}
