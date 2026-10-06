"""Holds the active Detector; deploy / rollback swap it without restarting the API."""

import threading
from pathlib import Path

import numpy as np
import pandas as pd

from ids.api.db import ModelVersion
from ids.bundle import Detector


class ModelService:
    def __init__(self, bundle_dir: str | Path):
        self.bundle_dir = Path(bundle_dir)
        self._lock = threading.RLock()
        self._detector: Detector | None = None

    @property
    def detector(self) -> Detector:
        with self._lock:
            if self._detector is None:
                raise RuntimeError("No active model")
            return self._detector

    @property
    def version(self) -> str | None:
        return self._detector.version if self._detector else None

    def activate(self, path: str | Path):
        det = Detector(path)                  # load fully before swapping in
        with self._lock:
            self._detector = det

    def load_active(self, db):
        mv = db.query(ModelVersion).filter_by(status="active").one_or_none()
        if mv:
            self.activate(mv.path)
        return mv

    # ---- helpers used by alerts / KR ----
    def features_frame(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows, columns=self.detector.pre.candidate_cols)

    def embed(self, feature_rows: list[dict]) -> np.ndarray:
        if not feature_rows:
            return np.zeros((0, 128), dtype="float32")
        return self.detector.score(self.features_frame(feature_rows))["embedding"]

    def evidence(self, features: dict, top_k: int = 6) -> list[dict]:
        """Features furthest from the training average (|z-score| after the transform).

        A simple, honest "why is this unusual" view for the analyst - not a full
        attribution method."""
        pre = self.detector.pre
        z = pre.transform(self.features_frame([features]))[0]
        order = np.argsort(-np.abs(z))[:top_k]
        return [{"feature": pre.feature_order[i], "value": features.get(pre.feature_order[i]),
                 "z": round(float(z[i]), 2),
                 "direction": "higher" if z[i] > 0 else "lower"} for i in order]
