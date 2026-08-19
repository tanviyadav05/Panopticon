"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class DnsPoisoningSimulator:
    name = "dns_poisoning"
    description = "DNS cache poisoning class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'parsing': float(rng.uniform(0.20,0.40)), 'connection': float(rng.uniform(0.05,0.15))}
