"""Mean +/- std tables over seeds, built from the saved val_metrics.json files."""

from pathlib import Path
import json

import numpy as np
import pandas as pd

HEADLINE = ["accuracy", "macro_f1", "macro_f1_reliable", "bin_precision",
            "detection_rate", "bin_f1", "fpr", "fnr"]


def load_runs(model_root: Path, classes, models=None, file="val_metrics.json") -> pd.DataFrame:
    rows = []
    for f in sorted(Path(model_root).glob(f"*/seed_*/{file}")):
        m = json.loads(f.read_text())
        if models and m["model"] not in models:
            continue
        b = m["binary"]
        row = {"model": m["model"], "seed": m["seed"], "accuracy": m["accuracy"],
               "macro_f1": m["macro_f1"], "macro_f1_reliable": m["macro_f1_reliable"],
               "weighted_f1": m["weighted_f1"], "bin_precision": b["precision"],
               "detection_rate": b["detection_rate"], "bin_f1": b["f1"], "fpr": b["fpr"],
               "fnr": b["fnr"], "train_s": m.get("train_seconds"),
               "ms_per_flow": m.get("predict_ms_per_flow")}
        row.update({f"recall:{c}": m["per_class"][c]["recall"] for c in classes})
        rows.append(row)
    return pd.DataFrame(rows)


def summarise(model_root: Path, out_stem: Path, classes, models=None, title="",
              file="val_metrics.json") -> pd.DataFrame:
    """Writes <out_stem>.csv (runs), <out_stem>_agg.csv and <out_stem>.md."""
    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    df = load_runs(model_root, classes, models, file)
    df.to_csv(out_stem.with_name(out_stem.name + "_runs.csv"), index=False)
    agg = df.drop(columns="seed").groupby("model").agg(["mean", "std"])
    if models:
        agg = agg.reindex([m for m in models if m in agg.index])
    agg.to_csv(out_stem.with_suffix(".csv"))

    def fmt(col, digits=2):
        return {mdl: f"{100 * agg.loc[mdl, (col, 'mean')]:.{digits}f} ± "
                     f"{100 * np.nan_to_num(agg.loc[mdl, (col, 'std')]):.{digits}f}"
                for mdl in agg.index}

    n_seeds = df.groupby("model").size().to_dict()
    cols = list(agg.index)
    lines = [f"# {title} (mean ± std over seeds, %)", "",
             "Seeds per model: " + ", ".join(f"{m}={n_seeds[m]}" for m in cols), "",
             "| metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for col in HEADLINE:
        v = fmt(col, 3 if col in ("fpr", "fnr") else 2)
        lines.append(f"| {col} | " + " | ".join(v[m] for m in cols) + " |")
    lines += ["", "## Per-class recall (%)", "",
              "| class | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for c in classes:
        v = fmt(f"recall:{c}")
        lines.append(f"| {c} | " + " | ".join(v[m] for m in cols) + " |")
    text = "\n".join(lines)
    out_stem.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text)
    return df
