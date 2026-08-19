"""Models the effect of a desync-class attack: probing for mismatched
request framing between an app and any intermediary, which manifests as
parsing/handling anomalies rather than raw resource exhaustion.

This is a SIMULATION — see ./README.md for why. step() returns a synthetic
nudge to the "parsing" pressure variable; it does not construct or send any
malformed request.
"""
from __future__ import annotations

import numpy as np


class DesyncSimulator:
    name = "parsing_pressure"
    description = "Request-framing-ambiguity class (desync-like): mismatched boundaries between app and intermediary."

    def step(self, rng: np.random.Generator) -> dict:
        magnitude = float(rng.uniform(0.10, 0.25))
        return {"parsing": magnitude}
