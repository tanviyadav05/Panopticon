"""SIMULATION only — see README.md. Returns pressure dict; never touches real network."""
from __future__ import annotations
import numpy as np

class StreamHijackSimulator:
    name = "stream_hijack"
    description = "RTSP/ONVIF stream hijack class."

    def step(self, rng: np.random.Generator) -> dict:
        return {'connection': float(rng.uniform(0.20,0.35)), 'cpu': float(rng.uniform(0.10,0.20))}
