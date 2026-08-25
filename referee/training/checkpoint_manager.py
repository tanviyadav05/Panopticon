"""Saves, loads, and rotates training checkpoints. Used by train.py during
training and evaluate.py to load a frozen policy.

Checkpoints land in experiments/checkpoints/<run_id>/ by default — see the
experiments/ directory's own note for why runs get their own folder rather
than overwriting a single latest.pt.
"""
from __future__ import annotations

import glob
import os
import time

import torch


class CheckpointManager:
    def __init__(self, checkpoint_dir: str, keep_last_n: int = 5):
        self.checkpoint_dir = checkpoint_dir
        self.keep_last_n = keep_last_n
        os.makedirs(checkpoint_dir, exist_ok=True)

    def save(self, iteration: int, state: dict) -> str:
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{iteration:08d}.pt")
        payload = {"iteration": iteration, "saved_at": time.time(), **state}
        torch.save(payload, path)
        self._rotate()
        return path

    def load_latest(self) -> dict | None:
        candidates = sorted(glob.glob(os.path.join(self.checkpoint_dir, "checkpoint_*.pt")))
        if not candidates:
            return None
        return torch.load(candidates[-1], map_location="cpu", weights_only=False)

    def load(self, path: str) -> dict:
        return torch.load(path, map_location="cpu", weights_only=False)

    def _rotate(self):
        candidates = sorted(glob.glob(os.path.join(self.checkpoint_dir, "checkpoint_*.pt")))
        excess = len(candidates) - self.keep_last_n
        for stale_path in candidates[:max(0, excess)]:
            os.remove(stale_path)
