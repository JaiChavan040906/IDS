"""Stage 5 - calibrate a trained CNN-LSTM, pick routing thresholds, build a bundle.

Usage:
    .venv/Scripts/python scripts/calibrate.py --model-dir artifacts/models/cnn_lstm/seed_42 --version v1
"""

import argparse
import json
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import yaml
from sklearn.model_selection import train_test_split

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ids.bundle import build_bundle  # noqa: E402
from ids.data import LABEL_COL, load_config, load_split  # noqa: E402
from ids.nn import load_model, predict  # noqa: E402
from ids.preprocessing import LabelEncoder, Preprocessor  # noqa: E402
from ids.uncertainty import (REVIEW, coverage_risk, ece, fit_uncertainty,  # noqa: E402
                             mahalanobis_sample, nll, normalized_entropy, route,
                             second_opinion, softmax)


def routing_summary(decision, pred, y):
    correct = pred == y
    auto = decision != REVIEW
    attack_true = y != 0
    return {
        "referral_rate": float((~auto).mean()),
        "error_overall": float((~correct).mean()),
        "error_on_auto_handled": float((~correct[auto]).mean()),
        "errors_caught_by_review": float((~correct & ~auto).sum() / max((~correct).sum(), 1)),
        "missed_attacks_auto_benign": int((attack_true & auto & (pred == 0)).sum()),
        "false_alarms_auto_alert": int((~attack_true & auto & (pred != 0)).sum()),
        "counts": {k: int((decision == k).sum()) for k in np.unique(decision)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="artifacts/models/cnn_lstm/seed_42")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--config", default="configs/uncertainty.yaml")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    dcfg = load_config()
    art = Path(dcfg["artifact_dir"])
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    model = load_model(args.model_dir)
    rep = Path(cfg["report_dir"])
    rep.mkdir(parents=True, exist_ok=True)
    K = len(enc.classes)

    # 1. TRAIN embeddings (for Mahalanobis class centres)
    tr = load_split("train", dcfg)
    y_all = enc.encode(tr[LABEL_COL])
    idx = mahalanobis_sample(y_all, cfg["mahalanobis_train_rows"], cfg["seed"])
    _, emb_tr = predict(model, pre.transform(tr.iloc[idx]), with_embeddings=True)
    y_tr = y_all[idx]
    del tr

    # 2. validation halves
    va = load_split("val", dcfg)
    yv = enc.encode(va[LABEL_COL])
    ia, ib = train_test_split(np.arange(len(va)), train_size=cfg["calibration_fraction"],
                              stratify=yv, random_state=cfg["seed"])
    Xv = pre.transform(va)
    logits, emb = predict(model, Xv, with_embeddings=True)

    # 3-4. temperature, Mahalanobis centres and thresholds - all fitted on the cal half
    T, ood, thresholds = fit_uncertainty(emb_tr, y_tr, logits[ia], emb[ia], yv[ia], K, cfg)
    del emb_tr
    dist = ood.score(emb)
    p_raw, p_cal = softmax(logits[ib]), softmax(logits[ib], T)
    ece_raw, bins_raw = ece(p_raw, yv[ib])
    ece_cal, bins_cal = ece(p_cal, yv[ib])
    calibration = {"nll_before": nll(p_raw, yv[ib]), "nll_after": nll(p_cal, yv[ib]),
                   "ece_before": ece_raw, "ece_after": ece_cal}
    print(f"T = {T:.3f} | ECE {ece_raw:.5f} -> {ece_cal:.5f} | "
          f"NLL {calibration['nll_before']:.5f} -> {calibration['nll_after']:.5f}")
    print("thresholds", thresholds)

    # 4b. second opinion (hybrid): RF uncertainty threshold, also from the cal half
    rf = joblib.load(cfg["second_opinion_model"]) if cfg.get("second_opinion_model") else None
    if rf is not None:
        rf_probs = rf.predict_proba(Xv)
        thresholds["rf_uncertainty"] = float(np.quantile(1 - rf_probs[ia].max(1),
                                                         1 - cfg["rf_referral_rate"]))
        thresholds["rf_referral_rate"] = cfg["rf_referral_rate"]
        print("rf threshold", thresholds["rf_uncertainty"])

    # 5. evaluate routing on eval half
    pred_b, ent_b = p_cal.argmax(1), normalized_entropy(p_cal)
    y_b = yv[ib]
    dec_cnn = route(pred_b, ent_b, dist[ib], thresholds["entropy"], thresholds["distance"])
    dec = dec_cnn
    if rf is not None:
        so = second_opinion(rf_probs[ib], rf.classes_, pred_b, thresholds["rf_uncertainty"])
        dec = route(pred_b, ent_b, dist[ib], thresholds["entropy"], thresholds["distance"],
                    extra_unsure=so["mask"])
    summary = {
        "temperature": T, "calibration": calibration, "thresholds": thresholds,
        "hybrid": rf is not None,
        "routing_eval_half": routing_summary(dec, pred_b, y_b),
        "routing_cnn_only": routing_summary(dec_cnn, pred_b, y_b),
        "routing_entropy_only": routing_summary(
            route(pred_b, ent_b, np.zeros_like(ent_b), thresholds["entropy"], np.inf), pred_b, y_b),
        "review_rate_by_true_class": {
            c: float((dec[y_b == k] == REVIEW).mean()) for k, c in enumerate(enc.classes)
            if (y_b == k).any()},
    }
    print(json.dumps(summary["routing_eval_half"], indent=1))

    # 6. coverage-risk curves: CNN-LSTM vs baselines' own confidence
    curves = {"CNN-LSTM entropy (calibrated)": (ent_b, pred_b == y_b),
              "CNN-LSTM 1 - max prob (raw)": (1 - p_raw.max(1), p_raw.argmax(1) == y_b)}
    Xb = Xv[ib]
    for name in ("random_forest", "lightgbm"):
        f = Path(f"artifacts/models/{name}/seed_42/model.joblib")
        if f.exists():
            pb = joblib.load(f).predict_proba(Xb)
            curves[f"{name} 1 - max prob"] = (1 - pb.max(1), pb.argmax(1) == y_b)
    fig, ax = plt.subplots(figsize=(7, 5))
    table = {}
    for name, (u, c) in curves.items():
        r, risk = coverage_risk(u, c)
        ax.plot(100 * r, 100 * risk, label=name)
        table[name] = {f"risk_at_{int(q * 100)}pct_referral":
                       float(risk[np.searchsorted(r, q)]) for q in (0.0, 0.01, 0.02, 0.05)}
    ax.set_xlim(0, 5)
    ax.set_xlabel("Referral rate to analyst (%)")
    ax.set_ylabel("Error rate on auto-handled flows (%)")
    ax.set_title("Coverage-risk (validation eval half)")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(rep / "coverage_risk.png", dpi=130); plt.close(fig)
    summary["coverage_risk"] = table

    # reliability diagram
    fig, ax = plt.subplots(figsize=(5, 5))
    for lab, bins in (("before", bins_raw), ("after T", bins_cal)):
        ax.plot([b["conf"] for b in bins], [b["acc"] for b in bins], "o-", label=lab)
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.set_xlabel("Confidence"); ax.set_ylabel("Accuracy"); ax.legend()
    ax.set_title(f"Reliability (T = {T:.2f})")
    fig.tight_layout(); fig.savefig(rep / "reliability.png", dpi=130); plt.close(fig)

    (rep / f"calibration_{args.version}.json").write_text(json.dumps(summary, indent=2))

    # 7. bundle
    val_metrics = json.loads((Path(args.model_dir) / "val_metrics.json").read_text())
    d = build_bundle(Path(cfg["bundle_dir"]) / args.version, args.model_dir, art, T,
                     calibration, ood, thresholds,
                     {"source_model": str(args.model_dir), "parent": None,
                      "trained_on": "train split", "val_metrics": {
                          k: val_metrics[k] for k in ("accuracy", "macro_f1", "macro_f1_reliable")}
                      | {"binary": val_metrics["binary"]},
                      "routing": summary["routing_eval_half"],
                      "hybrid_second_opinion": cfg.get("second_opinion_model")},
                     second_opinion_path=cfg.get("second_opinion_model"))
    print(f"Bundle written to {d}")


if __name__ == "__main__":
    main()
