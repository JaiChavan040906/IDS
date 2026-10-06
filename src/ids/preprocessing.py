"""The fitted feature transform shared by training, evaluation and the portal.

Fit ONLY on the training split. Save it, and load the same object everywhere
else so the portal applies exactly the transform the model was trained with.

Steps (in order):
  1. +/-Infinity -> NaN, then NaN -> train median
  2. signed log:  sign(x) * log1p(|x|)   (flow features span ~10 orders of
     magnitude; this stops a few huge values dominating the network)
  3. feature selection (decided on train): drop constant features, then drop a
     feature if |corr| > threshold with an already-kept feature
  4. standardise with train mean / std
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def signed_log1p(X: np.ndarray) -> np.ndarray:
    """In place (saves RAM on ~1M-row arrays)."""
    neg = X < 0
    np.abs(X, out=X)
    np.log1p(X, out=X)
    X[neg] *= -1
    return X


class Preprocessor:
    def __init__(self, corr_threshold: float = 0.99, corr_sample_rows: int = 300_000,
                 seed: int = 42):
        self.corr_threshold = corr_threshold
        self.corr_sample_rows = corr_sample_rows
        self.seed = seed

    # ---- fitting (train only) ----
    def fit(self, df: pd.DataFrame, candidate_cols: list[str]) -> "Preprocessor":
        self.candidate_cols = list(candidate_cols)
        X = df[self.candidate_cols].to_numpy(dtype="float32", copy=True)
        X[~np.isfinite(X)] = np.nan
        self.medians = np.nanmedian(X, axis=0)
        X = signed_log1p(self._impute(X, self.medians))

        dropped = {}
        std = X.std(axis=0, dtype="float64")
        keep = [i for i, s in enumerate(std) if s > 0]
        for i in set(range(len(std))) - set(keep):
            dropped[self.candidate_cols[i]] = "constant on train"

        rng = np.random.default_rng(self.seed)
        n = min(self.corr_sample_rows, len(X))
        sample = X[rng.choice(len(X), n, replace=False)][:, keep].astype("float64")
        corr = np.abs(np.corrcoef(sample, rowvar=False))
        kept_local = []
        for j in range(len(keep)):
            hits = [k for k in kept_local if corr[j, k] > self.corr_threshold]
            if hits:
                dropped[self.candidate_cols[keep[j]]] = (
                    f"|corr| {corr[j, hits[0]]:.3f} with {self.candidate_cols[keep[hits[0]]]}")
            else:
                kept_local.append(j)
        self.selected_idx = np.array([keep[j] for j in kept_local])
        self.feature_order = [self.candidate_cols[i] for i in self.selected_idx]
        self.dropped = dropped

        Xs = X[:, self.selected_idx]
        self.mean = Xs.mean(axis=0, dtype="float64").astype("float32")
        self.scale = Xs.std(axis=0, dtype="float64").astype("float32")
        return self

    # ---- applying (anywhere) ----
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        missing = set(self.candidate_cols) - set(df.columns)
        if missing:
            raise ValueError(f"Input is missing features: {sorted(missing)}")
        X = df[self.candidate_cols].to_numpy(dtype="float32", copy=True)
        X[~np.isfinite(X)] = np.nan
        X = signed_log1p(self._impute(X, self.medians))[:, self.selected_idx]
        X -= self.mean
        X /= self.scale
        return X

    @staticmethod
    def _impute(X, medians):
        nan = np.isnan(X)
        if nan.any():
            X[nan] = np.take(medians, np.nonzero(nan)[1])
        return X

    # ---- persistence ----
    def save(self, directory: str | Path):
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, d / "preprocessor.joblib")
        (d / "feature_order.json").write_text(json.dumps(self.feature_order, indent=2))
        (d / "candidate_features.json").write_text(json.dumps(self.candidate_cols, indent=2))
        (d / "dropped_features.json").write_text(json.dumps(self.dropped, indent=2))

    @staticmethod
    def load(directory: str | Path) -> "Preprocessor":
        return joblib.load(Path(directory) / "preprocessor.joblib")


class LabelEncoder:
    """Fixed class <-> index mapping, saved next to the preprocessor."""

    def __init__(self, classes: list[str]):
        self.classes = list(classes)
        self.index = {c: i for i, c in enumerate(self.classes)}

    def encode(self, labels) -> np.ndarray:
        return np.array([self.index[str(l)] for l in labels], dtype="int64")

    def decode(self, idx) -> list[str]:
        return [self.classes[i] for i in idx]

    def save(self, directory: str | Path):
        Path(directory, "label_map.json").write_text(json.dumps(self.index, indent=2))

    @staticmethod
    def load(directory: str | Path) -> "LabelEncoder":
        index = json.loads(Path(directory, "label_map.json").read_text())
        return LabelEncoder(sorted(index, key=index.get))
