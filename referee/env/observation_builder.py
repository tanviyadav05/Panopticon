"""Turns raw telemetry (from either ArenaSimulation in sim mode, or
Observer's real aggregator in live mode) into a per-agent observation
vector.

Both agents are encoded through the *same* canonical schema/encoder that
observer/pipeline/state_encoder.py defines, so a policy trained in sim mode
sees exactly the same vector shape and normalization it would see live. On
top of that shared encoding, each agent gets a different *subset* of
fields — Blue, as the system owner, has full internal telemetry visibility;
Red only gets the network-level and externally-visible signals an outside
attacker could plausibly infer from its own requests' behavior.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_OBSERVER_PIPELINE = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", "observer", "pipeline"))
sys.path.insert(0, _OBSERVER_PIPELINE)
from state_encoder import StateEncoder  # noqa: E402  (path must be set up first)

# Red only gets externally-inferable signals: connection-level symptoms and
# the error rate it experiences directly on its own requests. Everything
# else (memory, process internals, raw syscall rate, request volume) is
# internal telemetry Blue has and Red doesn't.
RED_VISIBLE_FIELDS = [
    "network.total_connections",
    "network.established",
    "network.close_wait",
    "network.syn_sent",
    "network.bytes_sent_rate",
    "network.bytes_recv_rate",
    "http.error_rate",
]


class ObservationBuilder:
    def __init__(self):
        self.encoder = StateEncoder()
        all_names = self.encoder.field_names()
        self._red_indices = [all_names.index(n) for n in RED_VISIBLE_FIELDS]
        self._blue_indices = list(range(len(all_names)))

    def size_for(self, agent: str) -> int:
        return len(self._red_indices) if agent == "red" else len(self._blue_indices)

    def build(self, agent: str, raw: dict) -> np.ndarray:
        full = self.encoder.encode(raw)
        indices = self._red_indices if agent == "red" else self._blue_indices
        return full[indices].astype(np.float32)
