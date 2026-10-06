"""Train the cWGAN-GP on minority TRAIN rows and write filtered synthetic samples.

Outputs
  artifacts/augment/generator.pt, synthetic.npz (X, y in transformed space)
  reports/augment/augment_report.json / .md  (counts, filter acceptance, quality)

Quality check per class: a small classifier tries to tell real from synthetic.
AUC 0.5 = indistinguishable, 1.0 = trivially fake.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import torch
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from ids.augment import sample, train_cwgan
from ids.data import LABEL_COL, load_config, load_split
from ids.preprocessing import LabelEncoder, Preprocessor


def real_vs_fake_auc(real, fake, seed):
    n = min(len(real), len(fake), 3000)
    rng = np.random.default_rng(seed)
    X = np.concatenate([real[rng.choice(len(real), n, replace=False)],
                        fake[rng.choice(len(fake), n, replace=False)]])
    y = np.r_[np.zeros(n), np.ones(n)]
    Xa, Xb, ya, yb = train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)
    clf = RandomForestClassifier(200, n_jobs=-1, random_state=seed).fit(Xa, ya)
    return float(roc_auc_score(yb, clf.predict_proba(Xb)[:, 1]))


def main():
    cfg = yaml.safe_load(open("configs/augment.yaml", encoding="utf-8"))
    dcfg = load_config()
    art = Path(dcfg["artifact_dir"])
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    tr = load_split("train", dcfg)
    X, y = pre.transform(tr), enc.encode(tr[LABEL_COL])
    del tr

    counts = np.bincount(y, minlength=len(enc.classes))
    targets = {c: cfg["target"] - int(counts[c]) for c in range(len(enc.classes))
               if cfg["min_real"] <= counts[c] < cfg["target"]}
    print("Augmenting:", {enc.classes[c]: f"{counts[c]} -> {cfg['target']}" for c in targets})

    mask = np.isin(y, list(targets))
    G, history = train_cwgan(X[mask], y[mask], len(enc.classes), cfg["gan"], cfg["seed"])

    rf = joblib.load(cfg["filter_model"])
    out_X, out_y, per_class = [], [], {}
    for c, need in targets.items():
        raw = sample(G, c, need * cfg["oversample"])
        ok = raw[rf.predict(raw) == c]
        keep = ok[:need]
        real = X[y == c]
        per_class[enc.classes[c]] = {
            "real_train_rows": int(counts[c]),
            "requested": need,
            "filter_acceptance": round(len(ok) / len(raw), 4),
            "kept": len(keep),
            "real_vs_fake_auc_unfiltered": round(real_vs_fake_auc(real, raw, cfg["seed"]), 4),
            "real_vs_fake_auc_kept": round(real_vs_fake_auc(real, keep, cfg["seed"]), 4)
            if len(keep) > 50 else None,
            "mean_abs_feature_mean_gap_std_units": round(
                float(np.abs(real.mean(0) - keep.mean(0)).mean()), 4) if len(keep) else None,
        }
        out_X.append(keep)
        out_y.append(np.full(len(keep), c, dtype="int64"))
        print(f"  {enc.classes[c]:<18} {per_class[enc.classes[c]]}")

    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "synthetic.npz", X=np.concatenate(out_X), y=np.concatenate(out_y))
    torch.save(G.state_dict(), out / "generator.pt")

    rep = Path(cfg["report_dir"])
    rep.mkdir(parents=True, exist_ok=True)
    report = {"config": cfg, "per_class": per_class, "history": history,
              "total_synthetic": int(sum(len(v) for v in out_y))}
    (rep / "augment_report.json").write_text(json.dumps(report, indent=2))
    lines = ["# cWGAN-GP augmentation", "",
             "| class | real | added | filter acceptance | real-vs-fake AUC (kept) |",
             "|---|---|---|---|---|"]
    for k, v in per_class.items():
        lines.append(f"| {k} | {v['real_train_rows']} | {v['kept']} | "
                     f"{100 * v['filter_acceptance']:.1f}% | {v['real_vs_fake_auc_kept']} |")
    lines += ["", "AUC 0.5 = synthetic indistinguishable from real; 1.0 = trivially fake."]
    (rep / "augment_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
