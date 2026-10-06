"""Stage 3 - train baseline models and evaluate them on the VALIDATION split.

For each model x seed:
    artifacts/models/<model>/seed_<s>/model.joblib + val_metrics.json
Summary (mean +/- std over seeds):
    reports/baselines/val_summary.csv, val_summary.md, confusion_<model>.png

Usage:
    .venv/Scripts/python scripts/train_baselines.py [--models random_forest lightgbm] [--seeds 42]
"""

import argparse
import time
from pathlib import Path

import joblib
import lightgbm as lgb
import yaml
from sklearn.ensemble import RandomForestClassifier

from ids.data import LABEL_COL, load_config, load_split
from ids.metrics import compute_metrics, plot_confusion, save_metrics
from ids.reporting import summarise
from ids.preprocessing import LabelEncoder, Preprocessor


def build(name: str, params: dict, seed: int):
    if name == "random_forest":
        return RandomForestClassifier(random_state=seed, **params)
    if name == "lightgbm":
        return lgb.LGBMClassifier(random_state=seed, **params)
    raise ValueError(name)


def fit(name, model, X, y, Xv, yv, cfg):
    if name == "lightgbm":
        model.fit(X, y, eval_set=[(Xv, yv)],
                  callbacks=[lgb.early_stopping(cfg["lightgbm_early_stopping_rounds"],
                                                verbose=False)])
        return {"best_iteration": int(model.best_iteration_)}
    model.fit(X, y)
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/baselines.yaml")
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--seeds", nargs="*", type=int)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    dcfg = load_config()
    art = Path(dcfg["artifact_dir"])
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    unreliable = dcfg.get("unreliable_classes", [])

    train, val = load_split("train", dcfg), load_split("val", dcfg)
    X, y = pre.transform(train), enc.encode(train[LABEL_COL])
    Xv, yv = pre.transform(val), enc.encode(val[LABEL_COL])
    del train, val
    print(f"train {X.shape}, val {Xv.shape}, {len(enc.classes)} classes", flush=True)

    out, rep = Path(cfg["output_dir"]), Path(cfg["report_dir"])
    rep.mkdir(parents=True, exist_ok=True)
    models = args.models or list(cfg["models"])
    seeds = args.seeds or cfg["seeds"]

    for name in models:
        for seed in seeds:
            d = out / name / f"seed_{seed}"
            print(f"\n== {name} seed {seed} ==", flush=True)
            model = build(name, cfg["models"][name], seed)

            t0 = time.time()
            extra = fit(name, model, X, y, Xv, yv, cfg)
            train_s = time.time() - t0

            t0 = time.time()
            pred = model.predict(Xv)
            ms_per_flow = 1000 * (time.time() - t0) / len(Xv)

            m = compute_metrics(yv, pred, enc.classes, unreliable)
            m.update(model=name, seed=seed, split="val", train_seconds=round(train_s, 1),
                     predict_ms_per_flow=round(ms_per_flow, 5), **extra)
            d.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, d / "model.joblib", compress=3)
            save_metrics(m, d / "val_metrics.json")
            if seed == seeds[0]:
                plot_confusion(m, enc.classes, rep / f"confusion_{name}.png",
                               f"{name} (seed {seed}) - validation")
            b = m["binary"]
            print(f"  {train_s:.0f}s | acc {m['accuracy']:.4f} macroF1 {m['macro_f1']:.4f} "
                  f"| binary F1 {b['f1']:.4f} DR {b['detection_rate']:.4f} FPR {b['fpr']:.5f} "
                  f"| {extra}", flush=True)
            del model

    summarise(out, rep / "val_summary", enc.classes, models=["random_forest", "lightgbm"],
              title="Baselines - validation set")


if __name__ == "__main__":
    main()
