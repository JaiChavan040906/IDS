"""Stage 2 - build the processed dataset and fit the preprocessing artifact.

  raw CSVs -> label mapping -> dedupe -> stratified 70/15/15 split
           -> fit Preprocessor on TRAIN only -> save everything

Outputs
  data/processed/{train,val,test}.parquet   untransformed features + label + meta
  artifacts/preprocessing/                  preprocessor.joblib, feature_order.json,
                                            label_map.json, data.yaml, prep_report.json

Usage:
    .venv/Scripts/python scripts/prepare_data.py [--config configs/data.yaml]
"""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np

from ids.data import (LABEL_COL, candidate_features, deduplicate, feature_hashes,
                      load_config, load_raw, split)
from ids.preprocessing import LabelEncoder, Preprocessor


def file_fingerprint(path: Path) -> str:
    """sha256 of the file, so every experiment records which data it used."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/data.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    t0 = time.time()

    print("1/5 Loading raw CSVs ...", flush=True)
    df = load_raw(cfg)
    features = candidate_features(df.columns, cfg)
    print(f"    {len(df):,} rows, {len(features)} candidate features")

    print("2/5 Removing duplicates and label conflicts ...", flush=True)
    df, dedup_stats = deduplicate(df, features)
    print(f"    removed {dedup_stats['duplicates_removed']:,} duplicates, "
          f"{dedup_stats['conflicting_rows_removed']:,} conflicting -> {len(df):,} rows")

    print("3/5 Stratified split ...", flush=True)
    parts = split(df, cfg)
    del df

    # Leakage check: no model-visible feature vector may appear in two splits.
    hashes = {k: set(feature_hashes(v, features)) for k, v in parts.items()}
    overlap = {f"{a}&{b}": len(hashes[a] & hashes[b])
               for a, b in [("train", "val"), ("train", "test"), ("val", "test")]}
    del hashes
    assert not any(overlap.values()), f"Feature vectors shared between splits: {overlap}"

    out = Path(cfg["processed_dir"])
    out.mkdir(parents=True, exist_ok=True)
    for name, part in parts.items():
        part.to_parquet(out / f"{name}.parquet", index=False)

    print("4/5 Fitting preprocessor on TRAIN only ...", flush=True)
    art = Path(cfg["artifact_dir"])
    pre = Preprocessor(cfg["feature_selection"]["corr_threshold"],
                       cfg["feature_selection"]["corr_sample_rows"], cfg["seed"])
    pre.fit(parts["train"], features)
    pre.save(art)
    # Class order: by train frequency, BENIGN first (index 0 = benign).
    classes = parts["train"][LABEL_COL].value_counts().index.astype(str).tolist()
    classes.remove("BENIGN")
    enc = LabelEncoder(["BENIGN", *classes])
    enc.save(art)
    shutil.copy(args.config, art / "data.yaml")

    # Sanity: transformed data must be finite and roughly standardised.
    Xv = pre.transform(parts["val"])
    assert np.isfinite(Xv).all(), "non-finite values after transform"
    print(f"    {len(pre.feature_order)} features kept, {len(pre.dropped)} dropped; "
          f"val mean {Xv.mean():+.3f}, std {Xv.std():.3f}")

    print("5/5 Writing report ...", flush=True)
    counts = {name: {k: int(v) for k, v in part[LABEL_COL].value_counts().items()}
              for name, part in parts.items()}
    report = {
        "dataset": cfg["dataset"],
        "raw_files": {p.name: file_fingerprint(p)
                      for p in sorted(Path(cfg["raw_dir"]).glob("*.csv"))},
        "seed": cfg["seed"],
        "use_dst_port": cfg["use_dst_port"],
        "dedup": dedup_stats,
        "split_sizes": {k: len(v) for k, v in parts.items()},
        "split_overlap_check": overlap,
        "class_counts": counts,
        "n_candidate_features": len(features),
        "n_selected_features": len(pre.feature_order),
        "selected_features": pre.feature_order,
        "dropped_features": pre.dropped,
        "classes": enc.classes,
        "seconds": round(time.time() - t0, 1),
    }
    (art / "prep_report.json").write_text(json.dumps(report, indent=2))

    print("\nClass counts (train / val / test):")
    for c in enc.classes:
        print(f"  {c:<20} {counts['train'].get(c, 0):>9,} {counts['val'].get(c, 0):>8,} "
              f"{counts['test'].get(c, 0):>8,}")
    print(f"\nDone in {report['seconds']}s. Artifacts in {art.resolve()}")


if __name__ == "__main__":
    main()
