"""Stage 4 - train the CNN-LSTM and evaluate on VALIDATION.

    artifacts/models/<name>/seed_<s>/{model.pt, model_config.json, history.json, val_metrics.json}

Usage:
    .venv/Scripts/python scripts/train_cnn_lstm.py                       # main model, 3 seeds
    .venv/Scripts/python scripts/train_cnn_lstm.py --no-lstm --name cnn_only --seeds 42
    .venv/Scripts/python scripts/train_cnn_lstm.py --augment artifacts/augment/synthetic.npz \
        --name cnn_lstm_aug
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import yaml

from ids.data import LABEL_COL, load_config, load_split
from ids.metrics import compute_metrics, plot_confusion, save_metrics
from ids.nn import DEVICE, predict, save_model, train
from ids.preprocessing import LabelEncoder, Preprocessor
from ids.reporting import summarise


def load_xy(dcfg):
    art = Path(dcfg["artifact_dir"])
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    tr, va = load_split("train", dcfg), load_split("val", dcfg)
    X, y = pre.transform(tr), enc.encode(tr[LABEL_COL])
    Xv, yv = pre.transform(va), enc.encode(va[LABEL_COL])
    return X, y, Xv, yv, enc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/cnn_lstm.yaml")
    ap.add_argument("--name", default="cnn_lstm")
    ap.add_argument("--no-lstm", action="store_true")
    ap.add_argument("--augment", help="npz with synthetic X, y (transformed space, train only)")
    ap.add_argument("--seeds", nargs="*", type=int)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    dcfg = load_config()
    X, y, Xv, yv, enc = load_xy(dcfg)
    if args.augment:
        syn = np.load(args.augment)
        X = np.concatenate([X, syn["X"].astype("float32")])
        y = np.concatenate([y, syn["y"].astype("int64")])
        print(f"+ {len(syn['y']):,} synthetic training rows from {args.augment}")
    print(f"device {DEVICE} | train {X.shape} | val {Xv.shape}", flush=True)

    out = Path(cfg["output_dir"])
    rep = Path(cfg["report_dir"])
    rep.mkdir(parents=True, exist_ok=True)
    seeds = args.seeds or cfg["seeds"]
    for seed in seeds:
        print(f"\n== {args.name} seed {seed} ==", flush=True)
        t0 = time.time()
        model, history = train(X, y, Xv, yv, len(enc.classes), cfg["train"], seed,
                               use_lstm=not args.no_lstm)
        train_s = time.time() - t0

        t0 = time.time()
        pred = predict(model, Xv).argmax(1)
        ms = 1000 * (time.time() - t0) / len(Xv)
        m = compute_metrics(yv, pred, enc.classes, dcfg.get("unreliable_classes", []))
        m.update(model=args.name, seed=seed, split="val", train_seconds=round(train_s, 1),
                 predict_ms_per_flow=round(ms, 5), epochs=len(history),
                 augment=args.augment, use_lstm=not args.no_lstm)

        d = out / args.name / f"seed_{seed}"
        save_model(model, d)
        (d / "history.json").write_text(json.dumps(history, indent=2))
        save_metrics(m, d / "val_metrics.json")
        if seed == seeds[0]:
            plot_confusion(m, enc.classes, rep / f"confusion_{args.name}.png",
                           f"{args.name} (seed {seed}) - validation")
        b = m["binary"]
        print(f"  {train_s:.0f}s | acc {m['accuracy']:.4f} macroF1 {m['macro_f1']:.4f} "
              f"| binary F1 {b['f1']:.4f} DR {b['detection_rate']:.4f} FPR {b['fpr']:.5f}",
              flush=True)

    summarise(out, rep / "val_summary", enc.classes,
              models=["random_forest", "lightgbm", "cnn_lstm", "cnn_lstm_aug", "cnn_only"],
              title="Stage 4 - CNN-LSTM vs baselines, validation set")


if __name__ == "__main__":
    main()
