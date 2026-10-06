"""Model bundle = everything the portal needs to score a raw flow, in one folder.

artifacts/bundles/<version>/
    model.pt, model_config.json     CNN-LSTM weights + architecture
    preprocessor.joblib             fitted transform (impute, log, select, scale)
    feature_order.json, candidate_features.json, label_map.json, data.yaml
    calibration.json                temperature + calibration metrics
    ood.npz                         Mahalanobis class means + precision matrix
    thresholds.json                 routing thresholds (entropy, distance, rf_uncertainty)
    second_opinion.joblib           (hybrid) Random Forest used as a second opinion
    manifest.json                   version, parent, source, metrics, created_at

`Detector` loads a bundle and turns raw flow rows (CSV columns) into decisions.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from ids.nn import load_model
from ids.preprocessing import LabelEncoder, Preprocessor
from ids.uncertainty import Mahalanobis, normalized_entropy, route, second_opinion, softmax

PREPROCESSING_FILES = ["preprocessor.joblib", "feature_order.json", "candidate_features.json",
                       "label_map.json", "data.yaml"]


def build_bundle(out_dir: str | Path, model_dir: str | Path, preprocessing_dir: str | Path,
                 temperature: float, calibration: dict, ood: Mahalanobis, thresholds: dict,
                 manifest: dict, second_opinion_path: str | Path | None = None) -> Path:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    if second_opinion_path:
        shutil.copy(second_opinion_path, d / "second_opinion.joblib")
    for f in ("model.pt", "model_config.json"):
        shutil.copy(Path(model_dir) / f, d / f)
    for f in PREPROCESSING_FILES:
        shutil.copy(Path(preprocessing_dir) / f, d / f)
    (d / "calibration.json").write_text(json.dumps({"temperature": temperature, **calibration},
                                                   indent=2))
    np.savez(d / "ood.npz", **ood.to_dict())
    (d / "thresholds.json").write_text(json.dumps(thresholds, indent=2))
    manifest = {"version": d.name, "created_at": datetime.now(timezone.utc).isoformat(),
                **manifest}
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return d


class Detector:
    """Raw flows in -> class, calibrated probabilities, uncertainty, routing decision."""

    def __init__(self, bundle_dir: str | Path, device: str = "cpu"):
        d = Path(bundle_dir)
        self.dir = d
        self.device = torch.device(device)
        self.pre = Preprocessor.load(d)
        self.enc = LabelEncoder.load(d)
        self.model = load_model(d, self.device)
        self.temperature = json.loads((d / "calibration.json").read_text())["temperature"]
        o = np.load(d / "ood.npz")
        self.ood = Mahalanobis.from_arrays(o["means"], o["precision"])
        self.thresholds = json.loads((d / "thresholds.json").read_text())
        self.manifest = json.loads((d / "manifest.json").read_text())
        so = d / "second_opinion.joblib"
        self.rf = joblib.load(so) if so.exists() else None
        if self.rf is not None:
            self.rf.n_jobs = 1          # small batches in the portal; avoid thread spin-up

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @torch.no_grad()
    def score_matrix(self, X: np.ndarray, batch: int = 2048) -> dict:
        """X already transformed. Returns arrays for every row."""
        logits, embs = [], []
        for i in range(0, len(X), batch):
            e = self.model.embed(torch.from_numpy(X[i:i + batch]).to(self.device))
            embs.append(e.cpu().numpy())
            logits.append(self.model.head(e).cpu().numpy())
        logits, emb = np.concatenate(logits), np.concatenate(embs)
        p = softmax(logits, self.temperature)
        pred = p.argmax(1)
        ent = normalized_entropy(p)
        dist = self.ood.score(emb)
        th = self.thresholds
        # decision_cnn_only: the paper-style routing, kept for comparison in reports
        dec_cnn = route(pred, ent, dist, th["entropy"], th["distance"])
        out = {"probs": p, "pred": pred, "confidence": p.max(1), "entropy": ent,
               "distance": dist, "decision": dec_cnn, "decision_cnn_only": dec_cnn,
               "embedding": emb}
        if self.rf is not None:
            so = second_opinion(self.rf.predict_proba(X), self.rf.classes_, pred,
                                th["rf_uncertainty"])
            out.update(so)
            out["decision"] = route(pred, ent, dist, th["entropy"], th["distance"],
                                    extra_unsure=so["mask"])
        return out

    def score(self, flows: pd.DataFrame) -> dict:
        return self.score_matrix(self.pre.transform(flows))

    def explain(self, s: dict, i: int, top_k: int = 3) -> dict:
        """One row of score() output as a JSON-friendly dict."""
        p = s["probs"][i]
        top = np.argsort(-p)[:top_k]
        reasons = []
        if s["entropy"][i] > self.thresholds["entropy"]:
            reasons.append("less confident than usual (among the model's most uncertain 1%)")
        if s["distance"][i] > self.thresholds["distance"]:
            reasons.append("flow is unlike any training traffic (possible unseen attack)")
        second = None
        if "rf_pred" in s:
            rf_class = self.enc.classes[int(s["rf_pred"][i])]
            if s["disagree"][i]:
                reasons.append(f"second-opinion model disagrees (says {rf_class})")
            elif s["rf_unsure"][i]:
                reasons.append("second-opinion model is unsure")
            second = {"class": rf_class, "confidence": float(1 - s["rf_uncertainty"][i])}
        return {
            "predicted_class": self.enc.classes[int(s["pred"][i])],
            "confidence": float(s["confidence"][i]),
            "entropy": float(s["entropy"][i]),
            "distance": float(s["distance"][i]),
            "decision": str(s["decision"][i]),
            "reasons": reasons,
            "top_classes": [{"class": self.enc.classes[int(k)], "prob": float(p[k])} for k in top],
            "second_opinion": second,
            "model_version": self.version,
        }
