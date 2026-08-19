"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class DeauthFloodSimulator:
    name = "deauth_flood"
    description = "802.11 deauth flood class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'connection': float(rng.uniform(0.30,0.50))}
