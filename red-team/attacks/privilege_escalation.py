"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class PrivilegeEscalationSimulator:
    name = "privilege_escalation"
    description = "Local privilege escalation class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'cpu': float(rng.uniform(0.10,0.25)), 'memory': float(rng.uniform(0.15,0.30))}
