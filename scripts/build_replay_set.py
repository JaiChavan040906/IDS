"""Stage 7 prep - demo traffic = the untouched TEST split, plus analyst context.

Joins each test row back to its raw CSV row (day, id) to recover Src/Dst IP,
ports, protocol and timestamp. These columns are shown to the analyst as
context but are NEVER model inputs (the model only sees candidate_features).
The true label is kept in `hidden_label` for evaluation only.

Output: data/processed/replay.parquet, ordered by flow timestamp.
"""

from pathlib import Path

import pandas as pd

from ids.data import LABEL_COL, RAW_LABEL_COL, load_config, load_split

# Src Port, Dst Port, Protocol are numeric and already in the processed split.
CONTEXT = ["Src IP", "Dst IP", "Timestamp"]


def main():
    cfg = load_config()
    test = load_split("test", cfg)
    test["row_id"] = test["row_id"].astype("int64")
    parts = []
    for f in sorted(Path(cfg["raw_dir"]).glob("*.csv")):
        header = pd.read_csv(f, nrows=0).columns
        use = [h for h in header if h.strip() in {"id", *CONTEXT}]
        ctx = pd.read_csv(f, usecols=use)
        ctx.columns = [c.strip() for c in ctx.columns]
        ctx = ctx.rename(columns={"id": "row_id"})
        ctx["day"] = f.stem
        sub = test[test["day"].astype(str) == f.stem]
        parts.append(sub.merge(ctx, on=["day", "row_id"], how="left", validate="one_to_one"))
        print(f"{f.stem}: {len(sub):,} test flows")
    df = pd.concat(parts, ignore_index=True)
    assert df["Src IP"].notna().all(), "some test rows did not match a raw row"
    df = df.rename(columns={LABEL_COL: "hidden_label", RAW_LABEL_COL: "hidden_raw_label"})
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df = df.sort_values("Timestamp").reset_index(drop=True)
    out = Path(cfg["processed_dir"]) / "replay.parquet"
    df.to_parquet(out, index=False)
    print(f"{len(df):,} flows -> {out}")


if __name__ == "__main__":
    main()
