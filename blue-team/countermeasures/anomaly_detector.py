"""Consumes the full (Blue-visible) encoded telemetry vector and flags
statistical deviations from a learned baseline — the primary signal
blue_controller.py's policy acts on, and (before any RL policy is trained)
the thing the heuristic fallback in blue_controller.py uses directly.

If models/detection_model.pkl doesn't exist yet, this trains a quick
bootstrap IsolationForest on synthetic "calm" telemetry the first time it
runs, and saves it — so the repo works out of the box, but the intent is
that you retrain this on real baseline telemetry collected from your own
Arena before relying on it for anything.
"""
from __future__ import annotations

import os

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

_DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "detection_model.pkl")


def _synthetic_calm_baseline(n_samples: int, n_features: int, seed: int = 0) -> np.ndarray:
    """A rough stand-in for "what the 14-field encoded vector looks like
    when nothing is wrong": mostly-low values with a bit of normal noise.
    Used only to bootstrap a usable model on a fresh checkout; see the
    module docstring."""
    rng = np.random.default_rng(seed)
    base = rng.normal(loc=0.15, scale=0.05, size=(n_samples, n_features))
    return np.clip(base, 0.0, 1.0).astype(np.float32)


class AnomalyDetector:
    def __init__(self, model_path: str | None = None, n_features: int = 14, contamination: float = 0.08):
        self.model_path = model_path or _DEFAULT_MODEL_PATH
        self.n_features = n_features
        self.contamination = contamination
        self.model = self._load_or_bootstrap()

    def _load_or_bootstrap(self) -> IsolationForest:
        if os.path.exists(self.model_path):
            return joblib.load(self.model_path)
        model = self.train(_synthetic_calm_baseline(2000, self.n_features))
        self.save(model)
        return model

    def train(self, baseline_features: np.ndarray) -> IsolationForest:
        model = IsolationForest(contamination=self.contamination, random_state=0, n_estimators=150)
        model.fit(baseline_features)
        return model

    def save(self, model: IsolationForest | None = None):
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(model or self.model, self.model_path)

    def anomaly_score(self, feature_vector: np.ndarray) -> float:
        """Higher = more anomalous. IsolationForest's score_samples is the
        opposite convention (lower = more anomalous), so this flips it."""
        return float(-self.model.score_samples(feature_vector.reshape(1, -1))[0])

    def is_anomalous(self, feature_vector: np.ndarray, threshold: float = 0.55) -> bool:
        return self.anomaly_score(feature_vector) >= threshold


if __name__ == "__main__":
    # Re-bootstrap the model file from scratch, e.g. after deleting it or
    # changing contamination/n_features.
    detector = AnomalyDetector()
    detector.save()
    print(f"detection_model.pkl trained/saved at {detector.model_path}")
    calm = _synthetic_calm_baseline(1, detector.n_features, seed=123)[0]
    spike = np.clip(calm + 0.6, 0, 1)
    print("calm sample anomaly score:   ", round(detector.anomaly_score(calm), 3))
    print("spiked sample anomaly score: ", round(detector.anomaly_score(spike), 3))
