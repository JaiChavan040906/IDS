"""Loading, cleaning, label mapping, de-duplication and splitting.

Everything here runs BEFORE any model sees the data. Nothing here is fitted,
so it is safe to run on the whole dataset (no train/test leakage).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

META_COLS = ["day", "row_id"]  # where a row came from; never a model input
LABEL_COL = "label"
RAW_LABEL_COL = "raw_label"


def load_config(path="configs/data.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def candidate_features(columns, cfg) -> list[str]:
    """Numeric columns the model is allowed to use (before feature selection)."""
    excluded = set(cfg["drop_columns"]) | {"Label", LABEL_COL, RAW_LABEL_COL, *META_COLS}
    if not cfg["use_dst_port"]:
        excluded.add("Dst Port")
    return [c for c in columns if c not in excluded]


def load_raw(cfg) -> pd.DataFrame:
    """Read all day files. String ID columns are skipped at read time to save RAM.

    Returns float32 features (all numeric columns incl. Dst Port) + raw_label,
    label, day, row_id.
    """
    skip = {"Flow ID", "Src IP", "Dst IP", "Timestamp", "Attempted Category"}
    frames = []
    for f in sorted(Path(cfg["raw_dir"]).glob("*.csv")):
        cols = [c.strip() for c in pd.read_csv(f, nrows=0).columns]
        header = pd.read_csv(f, nrows=0).columns
        use = [h for h, c in zip(header, cols) if c not in skip]
        df = pd.read_csv(f, usecols=use, low_memory=False)
        df.columns = [c.strip() for c in df.columns]

        df[RAW_LABEL_COL] = df.pop("Label").astype(str).str.strip()
        unknown = set(df[RAW_LABEL_COL]) - set(cfg["label_map"])
        if unknown:
            raise ValueError(f"{f.name}: labels missing from label_map: {unknown}")
        df[LABEL_COL] = df[RAW_LABEL_COL].map(cfg["label_map"])
        df["day"] = f.stem
        df = df.rename(columns={"id": "row_id"})

        num = [c for c in df.columns if c not in {RAW_LABEL_COL, LABEL_COL, *META_COLS}]
        df[num] = df[num].astype("float32")
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    for c in (RAW_LABEL_COL, LABEL_COL, "day"):
        df[c] = df[c].astype("category")
    return df


def deduplicate(df: pd.DataFrame, feature_cols: list[str]) -> tuple[pd.DataFrame, dict]:
    """Remove rows the model cannot tell apart.

    1. Rows with identical model features AND label -> keep one copy.
       (Otherwise a copy of a test row can sit in train and inflate scores.)
    2. Feature vectors that appear with more than one label -> drop all of them
       (no model can separate them; they only add label noise).
    Inf is treated as its own value here, so cleaning later does not matter.
    """
    feat_hash = pd.util.hash_pandas_object(df[feature_cols], index=False).to_numpy()
    lab_code = df[LABEL_COL].cat.codes.to_numpy()
    key = pd.DataFrame({"f": feat_hash, "l": lab_code})

    n0 = len(df)
    keep = ~key.duplicated()
    df, key = df[keep.to_numpy()], key[keep]

    labels_per_vector = key.groupby("f")["l"].transform("nunique").to_numpy()
    conflict = labels_per_vector > 1
    conflict_labels = df.loc[conflict, LABEL_COL].value_counts()
    df = df[~conflict].reset_index(drop=True)

    stats = {
        "rows_before": n0,
        "duplicates_removed": int(n0 - keep.sum()),
        "conflicting_rows_removed": int(conflict.sum()),
        "conflicting_rows_by_label": {k: int(v) for k, v in conflict_labels.items() if v},
        "rows_after": len(df),
    }
    return df, stats


def split(df: pd.DataFrame, cfg) -> dict[str, pd.DataFrame]:
    """Stratified train / val / test split (70/15/15 by default)."""
    s = cfg["split"]
    train, rest = train_test_split(df, train_size=s["train"], stratify=df[LABEL_COL],
                                   random_state=cfg["seed"])
    val_frac = s["val"] / (s["val"] + s["test"])
    val, test = train_test_split(rest, train_size=val_frac, stratify=rest[LABEL_COL],
                                 random_state=cfg["seed"])
    return {"train": train.reset_index(drop=True),
            "val": val.reset_index(drop=True),
            "test": test.reset_index(drop=True)}


def load_split(name: str, cfg) -> pd.DataFrame:
    return pd.read_parquet(Path(cfg["processed_dir"]) / f"{name}.parquet")


def feature_hashes(df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    return pd.util.hash_pandas_object(df[feature_cols], index=False).to_numpy()
