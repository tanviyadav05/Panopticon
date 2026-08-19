"""Models the effect of a hash-flooding-class attack: a volume of requests
engineered to trigger expensive server-side processing per request, which
stresses CPU-bound request handling rather than bandwidth or connections.

This is a SIMULATION — see ./README.md for why. step() returns a synthetic
nudge to the "cpu" pressure variable; it does not send any requests.
"""
from __future__ import annotations

import numpy as np


class HashFloodSimulator:
    name = "cpu_pressure"
    description = "CPU-exhaustion class (hash-flood-like): requests engineered to be expensive to process."

    def step(self, rng: np.random.Generator) -> dict:
        magnitude = float(rng.uniform(0.15, 0.35))
        return {"cpu": magnitude}
