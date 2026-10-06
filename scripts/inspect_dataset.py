"""Step 1 - Dataset inspection (EDA) for Improved CIC-IDS2017.

Reads every CSV in data/raw/ one file at a time (so memory stays manageable)
and reports:
  - column names (raw vs. cleaned), per-file column mismatches
  - duplicate column names and columns with identical content
  - class counts (overall and per file/day)
  - missing (NaN) and infinite values per column
  - constant (zero-variance) columns
  - duplicate rows: exact, and after dropping identifier columns
    (the second number is the one that matters for modelling)

Nothing is modified. Outputs go to reports/eda/.

Usage:
    .venv/Scripts/python scripts/inspect_dataset.py [--raw data/raw] [--out reports/eda]
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# Identifier / shortcut columns we will drop later (CLAUDE.md data rules).
# Compared after lower-casing and removing spaces/underscores.
ID_COLUMNS = {"id", "flowid", "srcip", "sourceip", "dstip", "destinationip",
              "srcport", "sourceport", "timestamp"}


def norm(name: str) -> str:
    return name.lower().replace(" ", "").replace("_", "")


def find_label_col(columns):
    for c in columns:
        if norm(c) == "label":
            return c
    raise ValueError(f"No 'Label' column found in: {list(columns)[:10]}...")


def row_hashes(df: pd.DataFrame) -> np.ndarray:
    return pd.util.hash_pandas_object(df, index=False).to_numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="reports/eda")
    args = ap.parse_args()

    raw, out = Path(args.raw), Path(args.out)
    files = sorted(raw.rglob("*.csv"))
    if not files:
        raise SystemExit(f"No CSV files found in {raw.resolve()}")
    out.mkdir(parents=True, exist_ok=True)

    per_file = []
    class_total = Counter()
    class_by_file = {}
    nan_counts = Counter()
    inf_counts = Counter()
    col_min, col_max = {}, {}
    col_content_hash = defaultdict(list)   # column -> list of per-file hashes
    all_hashes, feat_hashes = [], []
    label_hashes = []                      # to detect same features, different label
    reference_cols = None
    dup_name_cols = set()
    total_rows = 0

    for f in files:
        print(f"Reading {f.name} ...", flush=True)
        df = pd.read_csv(f, low_memory=False, encoding_errors="replace")
        raw_cols = list(df.columns)

        # Clean column names; pandas renames repeated names to "X.1", so
        # detect both exact repeats after stripping and ".1" suffixes.
        clean = [c.strip() for c in raw_cols]
        seen = Counter(clean)
        dup_name_cols.update(c for c, n in seen.items() if n > 1)
        dup_name_cols.update(c for c in clean
                             if c.endswith(".1") and c[:-2] in seen)
        df.columns = clean

        if reference_cols is None:
            reference_cols = clean
        missing_vs_ref = sorted(set(reference_cols) - set(clean))
        extra_vs_ref = sorted(set(clean) - set(reference_cols))

        label_col = find_label_col(clean)
        df[label_col] = df[label_col].astype(str).str.strip()
        counts = df[label_col].value_counts()
        class_by_file[f.name] = counts.to_dict()
        class_total.update(counts.to_dict())

        # Coerce everything except IDs/label to numeric to find bad cells.
        id_cols = [c for c in clean if norm(c) in ID_COLUMNS]
        # "Attempted Category" is label metadata (improved release), not a feature.
        other_cols = [c for c in clean if c not in id_cols and c != label_col
                      and norm(c) != "attemptedcategory"]
        num = df[other_cols].apply(pd.to_numeric, errors="coerce")
        non_numeric = {c: int(num[c].isna().sum() - df[c].isna().sum())
                       for c in other_cols
                       if num[c].isna().sum() > df[c].isna().sum()}

        for c in clean:
            nan_counts[c] += int(df[c].isna().sum())
        arr = num.to_numpy(dtype="float64")
        infs = np.isinf(arr).sum(axis=0)
        for c, n in zip(other_cols, infs):
            inf_counts[c] += int(n)

        finite = num.replace([np.inf, -np.inf], np.nan)
        for c in other_cols:
            lo, hi = finite[c].min(), finite[c].max()
            col_min[c] = lo if c not in col_min else np.nanmin([col_min[c], lo])
            col_max[c] = hi if c not in col_max else np.nanmax([col_max[c], hi])
            col_content_hash[c].append(
                int(pd.util.hash_pandas_object(num[c], index=False).sum()))

        # Row hashes: exact, and features-only (IDs + label dropped).
        all_hashes.append(row_hashes(df))
        feats = df[other_cols]
        feat_hashes.append(row_hashes(feats))
        label_hashes.append(pd.util.hash_pandas_object(
            df[label_col], index=False).to_numpy())

        per_file.append({
            "file": f.name,
            "rows": len(df),
            "columns": len(clean),
            "label_column": label_col,
            "id_columns_present": id_cols,
            "columns_missing_vs_first_file": missing_vs_ref,
            "extra_columns_vs_first_file": extra_vs_ref,
            "non_numeric_cells": non_numeric,
            "exact_duplicate_rows_within_file": int(df.duplicated().sum()),
        })
        total_rows += len(df)
        del df, num, finite, arr, feats

    # ---- Cross-file aggregates ----
    all_h = np.concatenate(all_hashes)
    feat_h = np.concatenate(feat_hashes)
    lab_h = np.concatenate(label_hashes)
    exact_dups = int(len(all_h) - len(np.unique(all_h)))
    feat_dups = int(len(feat_h) - len(np.unique(feat_h)))
    # Feature vectors that appear with more than one label = label conflicts.
    pairs = pd.DataFrame({"f": feat_h, "l": lab_h}).drop_duplicates()
    conflicting_vectors = int((pairs.groupby("f").size() > 1).sum())

    # Columns whose content is identical in every file.
    by_content = defaultdict(list)
    for c, hs in col_content_hash.items():
        by_content[tuple(hs)].append(c)
    identical_content = [cols for cols in by_content.values() if len(cols) > 1]

    constant_cols = sorted(c for c in col_min
                           if pd.notna(col_min[c]) and col_min[c] == col_max[c])
    negative_cols = sorted(c for c in col_min
                           if pd.notna(col_min[c]) and col_min[c] < 0)

    class_df = (pd.Series(class_total, name="count")
                .sort_values(ascending=False).to_frame())
    class_df["percent"] = (100 * class_df["count"] / total_rows).round(4)
    class_df.index.name = "label"
    class_df.to_csv(out / "class_counts.csv")
    pd.DataFrame(class_by_file).fillna(0).astype(int).to_csv(
        out / "class_counts_by_file.csv")

    col_df = pd.DataFrame({
        "nan": pd.Series(nan_counts),
        "inf": pd.Series(inf_counts),
        "min": pd.Series(col_min),
        "max": pd.Series(col_max),
    }).reindex(reference_cols)
    col_df.index.name = "column"
    col_df.to_csv(out / "column_stats.csv")

    summary = {
        "files": per_file,
        "total_rows": total_rows,
        "n_columns": len(reference_cols),
        "columns": reference_cols,
        "n_classes": len(class_total),
        "duplicate_column_names": sorted(dup_name_cols),
        "identical_content_columns": identical_content,
        "constant_columns": constant_cols,
        "columns_with_negative_values": negative_cols,
        "columns_with_nan": {c: n for c, n in nan_counts.items() if n},
        "columns_with_inf": {c: n for c, n in inf_counts.items() if n},
        "exact_duplicate_rows": exact_dups,
        "duplicate_rows_ignoring_ids": feat_dups,
        "feature_vectors_with_conflicting_labels": conflicting_vectors,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    # ---- Console report ----
    line = "-" * 70
    print(f"\n{line}\nFILES ({len(files)}), total rows: {total_rows:,}\n{line}")
    for p in per_file:
        print(f"  {p['file']:<45} {p['rows']:>10,} rows  {p['columns']} cols")
        if p["columns_missing_vs_first_file"] or p["extra_columns_vs_first_file"]:
            print(f"    missing: {p['columns_missing_vs_first_file']}  "
                  f"extra: {p['extra_columns_vs_first_file']}")
        if p["non_numeric_cells"]:
            print(f"    non-numeric cells: {p['non_numeric_cells']}")
    print(f"\n{line}\nCOLUMNS ({len(reference_cols)})\n{line}")
    print("  " + ", ".join(reference_cols))
    print(f"\n  Identifier columns to drop: "
          f"{[c for c in reference_cols if norm(c) in ID_COLUMNS]}")
    print(f"  Duplicate column names:     {sorted(dup_name_cols) or 'none'}")
    print(f"  Identical-content columns:  {identical_content or 'none'}")
    print(f"  Constant columns:           {constant_cols or 'none'}")
    print(f"  Columns with negatives:     {negative_cols or 'none'}")
    print(f"\n{line}\nCLASSES ({len(class_total)})\n{line}")
    for label, row in class_df.iterrows():
        print(f"  {label:<45} {int(row['count']):>10,}  {row['percent']:>8.4f}%")
    print(f"\n{line}\nMISSING / INFINITE\n{line}")
    print(f"  NaN: {summary['columns_with_nan'] or 'none'}")
    print(f"  Inf: {summary['columns_with_inf'] or 'none'}")
    print(f"\n{line}\nDUPLICATES\n{line}")
    print(f"  Exact duplicate rows:            {exact_dups:,} "
          f"({100 * exact_dups / total_rows:.2f}%)")
    print(f"  Duplicates after dropping IDs:   {feat_dups:,} "
          f"({100 * feat_dups / total_rows:.2f}%)")
    print(f"  Feature vectors with >1 label:   {conflicting_vectors:,}")
    print(f"\nReports written to {out.resolve()}")


if __name__ == "__main__":
    main()
