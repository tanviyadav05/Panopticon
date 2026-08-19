"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class ArpSpoofSimulator:
    name = "arp_spoof"
    description = "ARP spoofing / MITM class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'connection': float(rng.uniform(0.25,0.45))}
