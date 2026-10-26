"""Import an external CSV of network flows (CICFlowMeter-style) so it can be replayed
through the portal or scored offline.

Different CICFlowMeter versions name the same measurement differently, e.g.
    "Tot Fwd Pkts" (CSE-CIC-IDS2018)  =  "Total Fwd Packets" (CIC-IDS2017 original)
                                      =  "Total Fwd Packet"  (improved release, ours)
Column names are matched on a normalised bag of words, so word order, plurals and
common abbreviations do not matter. Measurements the file does not have are left
empty; the preprocessor fills them with the training median, and the import report
lists them so the user knows the results are less reliable.

Labels are optional. Known attack names are mapped to our 13 classes; anything we do
not recognise keeps its own name (and still counts as "attack" for detection metrics).
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

UNLABELLED = "UNLABELLED"
CONTEXT_COLS = ["Src IP", "Src Port", "Dst IP", "Dst Port", "Timestamp", "Label"]

# Share of the model's measurements a file must provide. Below MIN_COVERAGE the model
# would mostly see filled-in typical values, so its answers would be meaningless.
MIN_COVERAGE = 0.5
GOOD_COVERAGE = 0.9
FORMAT_HELP = ("The model needs network-flow measurements as produced by CICFlowMeter "
               "(e.g. 'Flow Duration', 'Total Fwd Packets', 'Fwd IAT Mean'). Convert packet "
               "captures (.pcap) with CICFlowMeter first; other flow formats (Zeek, NetFlow, "
               "KDD, UNSW-NB15) measure different things and are not supported.")

# token -> replacement tokens (abbreviations, synonyms, plurals)
TOKENS = {
    "totlen": ["total", "length"], "tot": ["total"], "len": ["length"],
    "pkts": ["packet"], "pkt": ["packet"], "packets": ["packet"],
    "byts": ["byte"], "bytes": ["byte"], "flags": ["flag"], "cnt": ["count"],
    "var": ["variance"], "blk": ["bulk"], "b": ["bulk"], "seg": ["segment"],
    "average": ["avg"], "backward": ["bwd"], "forward": ["fwd"],
    "source": ["src"], "destination": ["dst"],
    "cwe": ["cwr"],            # CSE-CIC-IDS2018 misspells the CWR flag column
    "of": [],
}

# label keyword -> our class; checked in order, first match wins
LABEL_RULES = [
    ("benign", "BENIGN"), ("normal", "BENIGN"),
    ("portscan", "Portscan"), ("port scan", "Portscan"),
    ("heartbleed", "Heartbleed"), ("hulk", "DoS Hulk"), ("goldeneye", "DoS GoldenEye"),
    ("slowloris", "DoS Slowloris"), ("slowhttp", "DoS Slowhttptest"),
    ("ddos", "DDoS"), ("loic", "DDoS"), ("hoic", "DDoS"),
    ("ftp", "FTP-Patator"), ("ssh", "SSH-Patator"), ("infil", "Infiltration"),
    ("xss", "Web Attack"), ("sql", "Web Attack"), ("web", "Web Attack"), ("bot", "Botnet"),
]


def canon(name: str) -> str:
    """Order-free normalised key for a column name."""
    name = re.sub(r"\.\d+$", "", str(name).strip())          # pandas duplicate suffix ".1"
    out = []
    for tok in re.findall(r"[a-z0-9]+", name.lower()):
        out.extend(TOKENS.get(tok, [tok]))
    return " ".join(sorted(out))


def map_label(raw, label_map: dict) -> str:
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none"):
        return UNLABELLED
    if s in label_map:
        return label_map[s]
    low = s.lower()
    for key, cls in LABEL_RULES:
        if key in low:
            return cls
    return s                                                 # unknown attack type: keep its name


def _count_rows(path: Path) -> int:
    with open(path, "rb") as f:
        return max(0, sum(1 for _ in f) - 1)


def import_flows(path, candidate_cols, label_map, out_dir, name=None, max_rows=300_000, seed=42):
    """Read a flow CSV, map its columns, keep up to max_rows rows (random sample),
    and save it as <out_dir>/<id>.parquet plus <id>.json (the import report)."""
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    header = list(pd.read_csv(path, nrows=0, encoding_errors="replace").columns)

    targets = {canon(c): c for c in candidate_cols}
    targets.update({canon(c): c for c in CONTEXT_COLS})
    rename = {}
    for h in header:
        t = targets.get(canon(h))
        if t and t not in rename.values():
            rename[h] = t
    n_match = sum(t in candidate_cols for t in rename.values())
    coverage = n_match / len(candidate_cols)
    if coverage < MIN_COVERAGE:
        raise ValueError(
            f"Only {n_match} of {len(candidate_cols)} required measurements were found in this file "
            f"({len(header)} columns). {FORMAT_HELP}")

    total = _count_rows(path)
    keep_frac = min(1.0, max_rows / total) if total else 1.0
    rng = np.random.default_rng(seed)
    parts = []
    for chunk in pd.read_csv(path, usecols=list(rename), chunksize=200_000, low_memory=False,
                             encoding_errors="replace"):
        chunk = chunk.rename(columns=rename)
        if "Label" in chunk:                                 # some files repeat the header row
            chunk = chunk[chunk["Label"].astype(str).str.strip() != "Label"]
        if keep_frac < 1.0:
            chunk = chunk[rng.random(len(chunk)) < keep_frac]
        parts.append(chunk)
    df = pd.concat(parts, ignore_index=False)
    df.index.name = "row_id"
    df = df.reset_index()

    found = [c for c in candidate_cols if c in df.columns]
    missing = [c for c in candidate_cols if c not in df.columns]
    for c in found:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    for c in missing:
        df[c] = np.float32(np.nan)

    labelled = "Label" in df.columns
    if labelled:
        raw = df.pop("Label").astype(str).str.strip()
        df["hidden_label"] = [map_label(x, label_map) for x in raw]
        unmapped = sorted({x for x in df["hidden_label"].unique()
                           if x not in set(label_map.values()) and x != UNLABELLED})
    else:
        df["hidden_label"] = UNLABELLED
        unmapped = []

    for c, default in (("Src IP", "unknown"), ("Dst IP", "unknown")):
        df[c] = df[c].astype(str) if c in df else default
    for c in ("Src Port", "Dst Port"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64") if c in df else 0
    if "Timestamp" in df:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", format="mixed", dayfirst=True)
        if df["Timestamp"].notna().mean() > 0.5:
            df = df.sort_values("Timestamp", kind="stable").reset_index(drop=True)
    else:
        df["Timestamp"] = pd.NaT

    ds_id = uuid.uuid4().hex[:10]
    df["day"] = name or path.stem
    df.to_parquet(out_dir / f"{ds_id}.parquet", index=False)

    counts = df["hidden_label"].value_counts()
    meta = {
        "id": ds_id,
        "name": name or path.stem,
        "file": path.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows_in_file": int(total),
        "rows_kept": int(len(df)),
        "sampled": keep_frac < 1.0,
        "labelled": bool(labelled and (df["hidden_label"] != UNLABELLED).any()),
        "label_counts": {k: int(v) for k, v in counts.head(20).items()},
        "attack_share": float((~df["hidden_label"].isin([UNLABELLED, "BENIGN"])).mean())
        if labelled else None,
        "unmapped_labels": unmapped,
        "features_found": len(found),
        "features_total": len(candidate_cols),
        "quality": "good" if coverage >= GOOD_COVERAGE else "partial",
        "quality_note": None if coverage >= GOOD_COVERAGE else
        f"Only {len(found)} of {len(candidate_cols)} measurements matched; the rest are filled with "
        "typical values, so results on this file are less reliable.",
        "columns_in_file": len(header),
        "columns_ignored": [h for h in header if h not in rename],
        "features_missing": missing,
        "column_renames": {k: v for k, v in rename.items() if k != v},
    }
    (out_dir / f"{ds_id}.json").write_text(json.dumps(meta, indent=2))
    return meta


def list_datasets(out_dir) -> list[dict]:
    d = Path(out_dir)
    if not d.exists():
        return []
    metas = [json.loads(p.read_text()) for p in d.glob("*.json")]
    return sorted(metas, key=lambda m: m["created_at"], reverse=True)
