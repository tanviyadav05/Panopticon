"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class CredentialStuffingSimulator:
    name = "credential_stuffing"
    description = "Auth brute-force class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'connection': float(rng.uniform(0.10,0.25)), 'cpu': float(rng.uniform(0.05,0.15))}
