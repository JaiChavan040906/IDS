"""Stage 7 - traffic replay: streams flows through the active model.

Traffic sources:
  "test"       the untouched TEST split of CIC-IDS2017 (built in)
  <dataset id> a CSV the admin uploaded (see ids.flow_import), e.g. CSE-CIC-IDS2018
               or traffic captured on another network

Each tick scores `batch_size` flows. auto_benign flows are only counted
(traffic_stats); auto_alert and review flows are stored as alerts.

The hidden label travels with the flow ONLY so the admin can measure live
accuracy. It is never passed to the model and never shown to the analyst.
Uploaded files may have no labels at all; then only the routing is measured.
"""

import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ids.api.db import Alert, SessionLocal, TrafficStat
from ids.flow_import import UNLABELLED, list_datasets
from ids.uncertainty import AUTO_BENIGN, REVIEW

CONTEXT_COLS = ["day", "row_id", "Timestamp", "Src IP", "Src Port", "Dst IP", "Dst Port",
                "Protocol", "hidden_label"]
TEST_SOURCE = "test"


def severity_for(pred_class: str, decision: str, cfg: dict) -> str:
    base = ("high" if pred_class in cfg["high"]
            else "medium" if pred_class in cfg["medium"] else "low")
    if decision == REVIEW and base != "low":
        return {"high": "medium", "medium": "low"}[base]
    return base


def _int(v, default=0) -> int:
    try:
        return int(v) if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


class ReplayService:
    def __init__(self, replay_file: str, models, app_cfg: dict):
        self.models = models
        self.cfg = dict(app_cfg["replay"])
        self.severity_cfg = app_cfg["severity"]
        self.replay_file = replay_file
        self.uploads_dir = Path(app_cfg.get("uploads_dir", "data/uploads"))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.processed = 0
        self.load_source(TEST_SOURCE)

    # ---- sources ----
    def datasets(self) -> list[dict]:
        built_in = {"id": TEST_SOURCE, "name": "CIC-IDS2017 test split (built in)",
                    "rows_kept": None, "labelled": True, "built_in": True}
        return [built_in] + list_datasets(self.uploads_dir)

    def load_source(self, source: str):
        if source == TEST_SOURCE:
            df, name = pd.read_parquet(self.replay_file), "CIC-IDS2017 test split (built in)"
        else:
            meta = next((m for m in list_datasets(self.uploads_dir) if m["id"] == source), None)
            if meta is None:
                raise ValueError(f"Unknown traffic source: {source}")
            df, name = pd.read_parquet(self.uploads_dir / f"{source}.parquet"), meta["name"]
        self.df = df
        self.labels = df["hidden_label"].astype(str).to_numpy()
        self.labelled = bool((self.labels != UNLABELLED).any())
        self.source, self.source_name = source, name
        if not self.labelled and self.cfg["mode"] == "attack_mix":
            self.cfg["mode"] = "sequential"     # attack mix needs to know which flows are attacks
        self._order, self.position = self._make_order(), 0

    # ---- ordering ----
    def _make_order(self) -> np.ndarray:
        n = len(self.df)
        if self.cfg["mode"] == "sequential" or not self.labelled:
            return np.arange(n)
        # attack_mix: shuffle, then keep attacks at ~attack_share of the stream
        rng = np.random.default_rng(self.cfg["seed"])
        attack = np.nonzero((self.labels != "BENIGN") & (self.labels != UNLABELLED))[0]
        benign = np.nonzero(self.labels == "BENIGN")[0]
        if len(attack) == 0 or len(benign) == 0:
            return np.arange(n)
        share = self.cfg["attack_share"]
        n_benign = min(len(benign), int(len(attack) * (1 - share) / share))
        order = np.concatenate([attack, rng.choice(benign, n_benign, replace=False)])
        rng.shuffle(order)
        return order

    # ---- control ----
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        return {"running": self.running, "position": self.position, "total": len(self._order),
                "processed": self.processed, "mode": self.cfg["mode"],
                "batch_size": self.cfg["batch_size"],
                "interval_seconds": self.cfg["interval_seconds"],
                "attack_share": self.cfg.get("attack_share"), "last_error": self.last_error,
                "source": self.source, "source_name": self.source_name,
                "labelled": self.labelled, "model_version": self.models.version}

    def configure(self, **kw):
        was_running = self.running
        self.stop()
        source = kw.pop("source", None)
        mode_changed = "mode" in kw and kw["mode"] != self.cfg["mode"]
        self.cfg.update({k: v for k, v in kw.items() if v is not None})
        if source and source != self.source:
            self.load_source(source)
        elif mode_changed or "attack_share" in kw:
            self._order, self.position = self._make_order(), 0
        if was_running:
            self.start()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="replay")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._thread = None

    def reset(self):
        self.stop()
        self.position = 0

    # ---- work ----
    def _loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                if self.position >= len(self._order):
                    break
                self.step()
                self.last_error = None
            except Exception as e:  # keep the thread alive; show the error to the admin
                self.last_error = f"{type(e).__name__}: {e}"
            self._stop.wait(max(0.0, self.cfg["interval_seconds"] - (time.time() - t0)))

    def step(self, n: int | None = None) -> dict:
        """Score the next batch and persist it. Also used directly by tests."""
        n = n or self.cfg["batch_size"]
        idx = self._order[self.position:self.position + n]
        if len(idx) == 0:
            return {"scored": 0}
        det = self.models.detector
        batch = self.df.iloc[idx]
        t0 = time.time()
        s = det.score(batch)                      # model sees candidate features only
        ms = 1000 * (time.time() - t0) / len(idx)

        truth = self.labels[idx]
        pred_names = np.array(det.enc.classes)[s["pred"]]
        dec = s["decision"]
        feats = batch[det.pre.candidate_cols]
        ctx = batch[CONTEXT_COLS]
        labelled = truth != UNLABELLED
        attack = labelled & (truth != "BENIGN")
        benign = truth == "BENIGN"

        db = SessionLocal()
        try:
            for j in np.nonzero(dec != AUTO_BENIGN)[0]:
                info = det.explain(s, j)
                r = ctx.iloc[j]
                f = {k: (None if not np.isfinite(v) else float(v))
                     for k, v in feats.iloc[j].items()}
                ts = pd.Timestamp(r["Timestamp"])
                db.add(Alert(
                    flow_day=str(r["day"]), flow_row_id=_int(r["row_id"]),
                    flow_time=None if pd.isna(ts) else ts.to_pydatetime(),
                    src_ip=str(r["Src IP"]), src_port=_int(r["Src Port"]),
                    dst_ip=str(r["Dst IP"]), dst_port=_int(r["Dst Port"]),
                    protocol=_int(r["Protocol"]), features=f,
                    embedding=s["embedding"][j].astype("float32").tobytes(),
                    model_version=det.version, predicted_class=info["predicted_class"],
                    confidence=info["confidence"], entropy=info["entropy"],
                    distance=info["distance"], decision=info["decision"],
                    reasons=info["reasons"], top_classes=info["top_classes"],
                    second_opinion=info["second_opinion"],
                    severity=severity_for(info["predicted_class"], info["decision"],
                                          self.severity_cfg),
                    hidden_label=str(truth[j]), source=self.source))
            db.add(TrafficStat(
                model_version=det.version, source=self.source, n_flows=len(idx),
                n_auto_benign=int((dec == AUTO_BENIGN).sum()),
                n_auto_alert=int((dec == "auto_alert").sum()),
                n_review=int((dec == REVIEW).sum()), ms_per_flow=ms,
                n_correct=int((labelled & (pred_names == truth)).sum()),
                n_missed_attacks=int((attack & (dec == AUTO_BENIGN)).sum()),
                n_labelled=int(labelled.sum()), n_attacks=int(attack.sum()),
                n_caught=int((attack & (dec != AUTO_BENIGN)).sum()),
                n_benign=int(benign.sum()),
                n_false_alarms=int((benign & (dec == "auto_alert")).sum())))
            db.commit()
        finally:
            db.close()
        self.position += len(idx)
        self.processed += len(idx)
        return {"scored": len(idx), "alerts": int((dec != AUTO_BENIGN).sum())}
