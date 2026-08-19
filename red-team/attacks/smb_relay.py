"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class SmbRelaySimulator:
    name = "smb_relay"
    description = "SMB NTLM relay class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'connection': float(rng.uniform(0.15,0.30)), 'parsing': float(rng.uniform(0.10,0.25))}
