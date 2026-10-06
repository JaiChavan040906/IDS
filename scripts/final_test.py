"""Evaluation step 1-4 - the ONE-TIME evaluation on the held-out TEST split.

Evaluates every trained model/seed (baselines, CNN-LSTM variants) plus the
deployed bundle's routing. Writes reports/final/ and a marker file recording
when the test set was used. Refuses to run twice unless --force (and says so
in the report), so nobody tunes on the test set by accident.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import joblib
import torch

from ids.bundle import Detector
from ids.data import LABEL_COL, load_config, load_split
from ids.metrics import compute_metrics, plot_confusion, save_metrics
from ids.nn import load_model, predict
from ids.preprocessing import LabelEncoder, Preprocessor
from ids.reporting import summarise
from ids.uncertainty import AUTO_BENIGN, REVIEW

PAPER = {"accuracy": 0.98, "detection_rate": 0.966, "precision": 0.921, "f1": 0.943}
MODELS = ["random_forest", "lightgbm", "cnn_lstm", "cnn_lstm_aug", "cnn_only"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="artifacts/bundles/v1")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out = Path("reports/final")
    marker = out / "TEST_SET_USED.json"
    if marker.exists() and not args.force:
        raise SystemExit(f"Test set already used ({marker.read_text().strip()}). "
                         "Re-running means you are no longer reporting an untouched test result. "
                         "Use --force only if you understand that.")
    out.mkdir(parents=True, exist_ok=True)

    dcfg = load_config()
    art = Path(dcfg["artifact_dir"])
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    te = load_split("test", dcfg)
    X, y = pre.transform(te), enc.encode(te[LABEL_COL])
    del te
    unreliable = dcfg.get("unreliable_classes", [])
    root = Path("artifacts/models")

    for name in MODELS:
        for d in sorted((root / name).glob("seed_*")):
            if (d / "model.joblib").exists():
                pred = joblib.load(d / "model.joblib").predict(X)
            elif (d / "model.pt").exists():
                pred = predict(load_model(d), X).argmax(1)
            else:
                continue
            seed = int(d.name.split("_")[1])
            m = compute_metrics(y, pred, enc.classes, unreliable)
            m.update(model=name, seed=seed, split="test")
            save_metrics(m, d / "test_metrics.json")
            if seed == 42:
                plot_confusion(m, enc.classes, out / f"confusion_{name}.png", f"{name} - TEST")
            print(f"{name} seed {seed}: acc {m['accuracy']:.4f} macroF1 {m['macro_f1']:.4f}")

    runs = summarise(root, out / "test_summary", enc.classes, models=MODELS,
                     title="Held-out TEST set", file="test_metrics.json")
    means = runs.drop(columns="seed").groupby("model").mean(numeric_only=True)

    # Deployed system: calibrated CNN-LSTM + routing
    det = Detector(args.bundle, device="cuda" if torch.cuda.is_available() else "cpu")
    s = det.score_matrix(X)
    att = y != 0

    def routing_stats(dec, pred):
        auto = dec != REVIEW
        return {
            "referral_rate": float((~auto).mean()),
            "accuracy_all": float((pred == y).mean()),
            "accuracy_on_auto_handled": float((pred[auto] == y[auto]).mean()),
            "errors_caught_by_review": float(((pred != y) & ~auto).sum() / max((pred != y).sum(), 1)),
            "attacks_missed_auto_benign": int((att & (dec == AUTO_BENIGN)).sum()),
            "attack_miss_rate": float((att & (dec == AUTO_BENIGN)).sum() / att.sum()),
            "benign_false_alerts": int((~att & (dec == "auto_alert")).sum()),
            "benign_false_alert_rate": float((~att & (dec == "auto_alert")).sum() / (~att).sum()),
            "review_rate_by_true_class": {c: float((dec[y == k] == REVIEW).mean())
                                          for k, c in enumerate(enc.classes) if (y == k).any()},
        }

    routing = {"bundle": det.version, "hybrid": det.rf is not None,
               **routing_stats(s["decision"], s["pred"]),
               "cnn_only": routing_stats(s["decision_cnn_only"], s["pred"])}
    (out / "routing_test.json").write_text(json.dumps(routing, indent=2))

    lines = ["# Final test-set results", "",
             f"Evaluated {datetime.now():%Y-%m-%d %H:%M}. Test split: {len(y):,} flows, never used "
             "for training, tuning, calibration or threshold selection.", "",
             "## Paper comparison (binary: attack vs benign)", "",
             "| | paper (reported) | " + " | ".join(MODELS) + " |", "|---|---|" + "---|" * len(MODELS)]
    for k, col in [("accuracy", "accuracy"), ("detection_rate", "detection_rate"),
                   ("precision", "bin_precision"), ("f1", "bin_f1")]:
        cells = [f"{100 * means.loc[m, col]:.2f}%" if m in means.index else "–" for m in MODELS]
        lines.append(f"| {k} | {100 * PAPER[k]:.1f}% | " + " | ".join(cells) + " |")
    lines += ["", "Our accuracy is 13-class accuracy; the paper's is binary accuracy.", "",
              "## Deployed system (calibrated CNN-LSTM + RF second opinion, hybrid routing)", "",
              f"- Sent to analyst: **{100 * routing['referral_rate']:.2f}%** of flows",
              f"- Accuracy on the flows handled automatically: **{100 * routing['accuracy_on_auto_handled']:.3f}%** "
              f"(vs {100 * routing['accuracy_all']:.3f}% if nothing were referred)",
              f"- Share of all model errors that land in the review queue: **{100 * routing['errors_caught_by_review']:.1f}%**",
              f"- Attacks auto-closed as benign: {routing['attacks_missed_auto_benign']} "
              f"({100 * routing['attack_miss_rate']:.3f}% of attacks)",
              f"- Benign flows raised as confident alerts: {routing['benign_false_alerts']} "
              f"({100 * routing['benign_false_alert_rate']:.4f}% of benign)",
              "", f"CNN-LSTM-only routing on the same flows (no RF second opinion): "
              f"referral {100 * routing['cnn_only']['referral_rate']:.2f}%, "
              f"auto-handled accuracy {100 * routing['cnn_only']['accuracy_on_auto_handled']:.3f}%, "
              f"errors caught {100 * routing['cnn_only']['errors_caught_by_review']:.1f}%, "
              f"attacks missed {routing['cnn_only']['attacks_missed_auto_benign']}.",
              "", "Full per-class tables: test_summary.md"]
    (out / "FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    marker.write_text(json.dumps({"used_at": datetime.now().isoformat(), "forced": args.force}))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
