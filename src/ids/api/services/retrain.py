"""Stage 11 - controlled retraining.

verified feedback -> candidate model -> evaluate on the FIXED benchmark and on
held-out feedback -> pass/fail against acceptance criteria that were copied
into the job when it was created -> the admin approves/rejects -> deploy.

Nothing here deploys automatically.

Data used:
  * verified analyst feedback (analyst's label, never the hidden label)
  * a stratified sample of the ORIGINAL train split (so the model does not
    forget old traffic while learning from a few hundred corrections)
  * fixed benchmark = validation "eval" half (same split as Stage 5)
"""

import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from ids.api.db import Alert, Feedback, ModelVersion, RetrainJob, SessionLocal, audit
from ids.bundle import Detector, build_bundle
from ids.data import LABEL_COL, load_split
from ids.metrics import compute_metrics
from ids.nn import DEVICE, fine_tune, load_model, predict, save_model
from ids.uncertainty import REVIEW, fit_uncertainty, mahalanobis_sample


def usable_feedback(db, classes):
    """Verified, decisive feedback whose label is a class the model knows."""
    rows = (db.query(Feedback, Alert).join(Alert, Alert.id == Feedback.alert_id)
            .filter(Feedback.verified.is_(True), Feedback.verdict.in_(["malicious", "benign"]))
            .all())
    out = []
    for fb, al in rows:
        label = "BENIGN" if fb.verdict == "benign" else fb.attack_class
        if label in classes:
            out.append((fb.id, al.features, label))
    return out


def split_feedback(y: np.ndarray, holdout: float, seed: int):
    """Stratify by label when every label has enough items, else split randomly."""
    counts = np.bincount(y)
    n_classes = int((counts > 0).sum())
    n_ho = int(np.ceil(len(y) * holdout))
    can_stratify = counts[counts > 0].min() >= 2 and min(n_ho, len(y) - n_ho) >= n_classes
    return train_test_split(np.arange(len(y)), test_size=n_ho, random_state=seed,
                            stratify=y if can_stratify else None)


def next_version(db) -> str:
    nums = [int(v[0][1:]) for v in db.query(ModelVersion.version).all() if v[0][1:].isdigit()]
    return f"v{max(nums, default=0) + 1}"


class RetrainService:
    def __init__(self, models, app_cfg: dict, data_cfg: dict, unc_cfg: dict):
        self.models = models
        self.cfg = app_cfg["retraining"]
        self.bundle_dir = Path(app_cfg["bundle_dir"])
        self.dcfg, self.ucfg = data_cfg, unc_cfg
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def create_job(self, db, username: str) -> RetrainJob:
        if self.busy:
            raise ValueError("A retraining job is already running")
        n = len(usable_feedback(db, self.models.detector.enc.classes))
        if n < self.cfg["min_verified_feedback"]:
            raise ValueError(f"Need at least {self.cfg['min_verified_feedback']} verified "
                             f"feedback items with a known class; have {n}")
        job = RetrainJob(created_by=username, status="queued", base_version=self.models.version,
                         n_feedback=n,
                         criteria={**self.cfg["acceptance"],
                                   "min_verified_feedback": self.cfg["min_verified_feedback"]})
        db.add(job)
        audit(db, username, "retrain.create", "job", base=job.base_version, n_feedback=n,
              criteria=job.criteria)
        db.commit()
        self._thread = threading.Thread(target=self._run, args=(job.id,), daemon=True)
        self._thread.start()
        return job

    # ------------------------------------------------------------------
    def _run(self, job_id: int):
        db = SessionLocal()
        job = db.get(RetrainJob, job_id)

        def log(msg):
            stamp = datetime.now().strftime("%H:%M:%S")
            job.log = (job.log or "") + f"[{stamp}] {msg}\n"
            db.commit()

        try:
            job.status = "running"
            db.commit()
            self._train_and_evaluate(db, job, log)
            job.status = "evaluated"
        except Exception as e:
            job.status = "failed"
            log(f"FAILED: {e}\n{traceback.format_exc()}")
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()

    def _train_and_evaluate(self, db, job, log):
        cfg, seed = self.cfg, self.dcfg["seed"]
        base_mv = db.query(ModelVersion).filter_by(version=job.base_version).one()
        base = Detector(base_mv.path, device=DEVICE.type)   # GPU for the big benchmark
        pre, enc = base.pre, base.enc
        K = len(enc.classes)

        # 1. feedback -> train / holdout
        fb = usable_feedback(db, enc.classes)
        fb_ids = [f[0] for f in fb]
        Xf = pre.transform(pd.DataFrame([f[1] for f in fb], columns=pre.candidate_cols))
        yf = enc.encode([f[2] for f in fb])
        i_tr, i_ho = split_feedback(yf, cfg["feedback_holdout_fraction"], seed)
        log(f"{len(yf)} verified feedback items: {len(i_tr)} for training, "
            f"{len(i_ho)} held out. Labels: "
            + ", ".join(f"{enc.classes[c]}={n}" for c, n in enumerate(np.bincount(yf, minlength=K)) if n))

        # 2. replay guard: stratified sample of the original train split
        tr = load_split("train", self.dcfg)
        y_tr_all = enc.encode(tr[LABEL_COL])
        idx = mahalanobis_sample(y_tr_all, cfg["base_train_rows"], seed)
        X_base, y_base = pre.transform(tr.iloc[idx]), y_tr_all[idx]
        del tr
        X = np.concatenate([X_base] + [Xf[i_tr]] * cfg["feedback_repeat"])
        y = np.concatenate([y_base] + [yf[i_tr]] * cfg["feedback_repeat"])
        log(f"Fine-tuning {job.base_version} on {len(X_base):,} original rows + "
            f"{len(i_tr)} feedback rows x{cfg['feedback_repeat']}")

        # 3. fine-tune a copy of the base model
        model = fine_tune(load_model(base_mv.path), X, y, cfg["epochs"], cfg["lr"], seed, log=log)

        # 4. recalibrate (same procedure as Stage 5)
        va = load_split("val", self.dcfg)
        yv = enc.encode(va[LABEL_COL])
        ia, ib = train_test_split(np.arange(len(va)), train_size=self.ucfg["calibration_fraction"],
                                  stratify=yv, random_state=self.ucfg["seed"])
        if cfg.get("benchmark_max_rows"):          # quick checks only (tests); normally unset
            rng = np.random.default_rng(seed)
            ia = np.sort(rng.choice(ia, min(len(ia), cfg["benchmark_max_rows"]), replace=False))
            ib = np.sort(rng.choice(ib, min(len(ib), cfg["benchmark_max_rows"]), replace=False))
        Xv = pre.transform(va)
        del va
        _, emb_tr = predict(model, X_base, with_embeddings=True)
        logits_v, emb_v = predict(model, Xv, with_embeddings=True)
        T, ood, thresholds = fit_uncertainty(emb_tr, y_base, logits_v[ia], emb_v[ia], yv[ia], K,
                                             self.ucfg)
        del emb_tr
        # The RF second opinion is not retrained; keep it and its threshold unchanged.
        second = base.dir / "second_opinion.joblib"
        for k in ("rf_uncertainty", "rf_referral_rate"):
            if k in base.thresholds:
                thresholds[k] = base.thresholds[k]
        log(f"Recalibrated: T={T:.3f}, thresholds entropy={thresholds['entropy']:.4f} "
            f"distance={thresholds['distance']:.1f}"
            + (" (RF second opinion kept from base)" if second.exists() else ""))

        version = next_version(db)
        tmp = self.bundle_dir / f"_{version}_model"
        save_model(model, tmp)
        path = build_bundle(self.bundle_dir / version, tmp, base.dir, T, {}, ood, thresholds,
                            {"parent": job.base_version, "source_model": f"retrain job {job.id}",
                             "trained_on": f"{len(X_base)} train rows + {len(i_tr)} feedback"},
                            second_opinion_path=second if second.exists() else None)
        for f in tmp.iterdir():
            f.unlink()
        tmp.rmdir()
        cand = Detector(path, device=DEVICE.type)

        # 5. evaluate base vs candidate on the fixed benchmark + held-out feedback
        def evaluate(det):
            s = det.score_matrix(Xv[ib])
            m = compute_metrics(yv[ib], s["pred"], enc.classes,
                                self.dcfg.get("unreliable_classes", []))
            fb_s = det.score_matrix(Xf[i_ho]) if len(i_ho) else None
            return {
                "benchmark_accuracy": m["accuracy"],
                "benchmark_macro_f1_reliable": m["macro_f1_reliable"],
                "benchmark_macro_f1": m["macro_f1"],
                "benchmark_fpr": m["binary"]["fpr"],
                "benchmark_detection_rate": m["binary"]["detection_rate"],
                "benchmark_referral_rate": float((s["decision"] == REVIEW).mean()),
                "feedback_holdout_accuracy":
                    float((fb_s["pred"] == yf[i_ho]).mean()) if fb_s else None,
                "feedback_train_accuracy":
                    float((det.score_matrix(Xf[i_tr])["pred"] == yf[i_tr]).mean()),
            }

        rb, rc = evaluate(base), evaluate(cand)
        a = job.criteria
        checks = {
            "macro_f1_drop": {
                "value": rb["benchmark_macro_f1_reliable"] - rc["benchmark_macro_f1_reliable"],
                "limit": a["max_macro_f1_drop"], "rule": "<="},
            "fpr_increase": {"value": rc["benchmark_fpr"] - rb["benchmark_fpr"],
                             "limit": a["max_fpr_increase"], "rule": "<="},
            "feedback_accuracy_gain": {
                "value": (rc["feedback_holdout_accuracy"] or 0) - (rb["feedback_holdout_accuracy"] or 0),
                "limit": a["min_feedback_accuracy_gain"], "rule": ">="},
        }
        for c in checks.values():
            c["passed"] = bool(c["value"] <= c["limit"] if c["rule"] == "<=" else c["value"] >= c["limit"])
        passed = all(c["passed"] for c in checks.values())
        for k in ("base", "candidate"):
            r = rb if k == "base" else rc
            log(f"{k:9s} macroF1(rel) {r['benchmark_macro_f1_reliable']:.4f} FPR "
                f"{r['benchmark_fpr']:.5f} feedback-holdout acc {r['feedback_holdout_accuracy']}")
        log("Acceptance: " + ("PASSED" if passed else "FAILED") + " - " +
            ", ".join(f"{k} {'ok' if c['passed'] else 'x'}" for k, c in checks.items()))

        db.add(ModelVersion(version=version, path=str(path), status="candidate",
                            parent=job.base_version,
                            metrics={"benchmark": rc, "base_benchmark": rb, "checks": checks,
                                     "passed": passed, "job_id": job.id},
                            notes=f"Retrained from {job.base_version} with {len(fb)} verified feedback"))
        job.candidate_version = version
        job.results = {"base": rb, "candidate": rc, "checks": checks, "feedback_ids": fb_ids,
                       "n_feedback_train": int(len(i_tr)), "n_feedback_holdout": int(len(i_ho))}
        job.passed = passed
        db.commit()
