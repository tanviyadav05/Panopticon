"""Models the effect of a Slowloris-class connection-exhaustion attack:
holding many partial connections open to tie up a server's connection pool.

This is a SIMULATION — see ./README.md for why. step() returns a synthetic
nudge to the "connection" pressure variable; it does not open any sockets.
"""
from __future__ import annotations

import numpy as np


class SlowlorisSimulator:
    name = "connection_pressure"
    description = "Connection-exhaustion class (Slowloris-like): many slow, partial connections."

    def step(self, rng: np.random.Generator) -> dict:
        magnitude = float(rng.uniform(0.15, 0.35))
        return {"connection": magnitude}
