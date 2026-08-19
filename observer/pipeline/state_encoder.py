"""Converts an aggregated window summary (a flat dict of dotted keys, as
produced by aggregator.Aggregator.flush()) into the fixed-length numeric
vector the RL environment expects — and back again for debugging.

referee/env/observation_builder.py loads the *same* state_schema.json so the
two sides can never silently drift out of field-order sync.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "state_schema.json")


def load_schema(path: str = _SCHEMA_PATH) -> dict:
    with open(path, "r") as fh:
        return json.load(fh)


class StateEncoder:
    def __init__(self, schema: Optional[dict] = None):
        self.schema = schema or load_schema()
        self.fields = self.schema["fields"]
        self.size = len(self.fields)

    def encode(self, summary: dict) -> np.ndarray:
        vec = np.zeros(self.size, dtype=np.float32)
        for i, field in enumerate(self.fields):
            raw = float(summary.get(field["source"], 0.0))
            vec[i] = self._normalize(raw, field["min"], field["max"])
        return vec

    def field_names(self) -> list[str]:
        return [f["name"] for f in self.fields]

    def decode(self, vec: np.ndarray) -> dict:
        """Inverse of encode(), useful for debugging/dashboards — maps a
        normalized vector back to approximate human-readable values."""
        out = {}
        for i, field in enumerate(self.fields):
            lo, hi = field["min"], field["max"]
            out[field["name"]] = lo + float(vec[i]) * (hi - lo)
        return out

    @staticmethod
    def _normalize(value: float, lo: float, hi: float) -> float:
        if hi <= lo:
            return 0.0
        clipped = max(lo, min(hi, value))
        return (clipped - lo) / (hi - lo)
