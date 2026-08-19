"""Models the effect of a JSON-bomb-class attack: oversized or deeply
nested payloads aimed at a parsing endpoint, stressing memory allocation
and parser resilience rather than connections or raw CPU.

This is a SIMULATION — see ./README.md for why. step() returns a synthetic
nudge to the "memory" pressure variable; it does not construct or send any
payload.
"""
from __future__ import annotations

import numpy as np


class JsonBombSimulator:
    name = "memory_pressure"
    description = "Memory-exhaustion class (JSON-bomb-like): oversized/nested payloads stressing parsing and allocation."

    def step(self, rng: np.random.Generator) -> dict:
        magnitude = float(rng.uniform(0.10, 0.30))
        return {"memory": magnitude}
