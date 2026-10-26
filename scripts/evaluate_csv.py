"""Score an external flow CSV with the deployed bundle and write a generalisation report.

Use this to answer "how does the model do on NEW data?" (e.g. a CSE-CIC-IDS2018 day,
or flows captured on another network) without going through the website.

    .venv/Scripts/python scripts/evaluate_csv.py path/to/flows.csv [--max-rows 500000]

Writes reports/external/<name>.md and .json. A Label column is optional; without it
only the routing (how much goes to review) can be reported.
"""

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from ids.bundle import Detector
from ids.data import load_config
from ids.flow_import import UNLABELLED, import_flows
from ids.uncertainty import AUTO_BENIGN, REVIEW


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--bundle", default="artifacts/bundles/v1")
    ap.add_argument("--max-rows", type=int, default=500_000)
    args = ap.parse_args()

    det = Detector(args.bundle, device="cuda" if torch.cuda.is_available() else "cpu")
    with tempfile.TemporaryDirectory() as tmp:
        meta = import_flows(args.csv, det.pre.candidate_cols, load_config()["label_map"], tmp,
                            max_rows=args.max_rows)
        df = pd.read_parquet(Path(tmp) / f"{meta['id']}.parquet")
    print(f"{meta['rows_kept']:,} flows, {meta['features_found']}/{meta['features_total']} "
          f"measurements matched, labelled={meta['labelled']}")

    s = det.score(df)
    dec, pred = s["decision"], np.array(det.enc.classes)[s["pred"]]
    truth = df["hidden_label"].astype(str).to_numpy()
    lab = truth != UNLABELLED
    att, ben = lab & (truth != "BENIGN"), truth == "BENIGN"

    def r(a, b):
        return float(a / b) if b else None

    res = {
        "file": meta["file"], "bundle": det.version, "import": meta,
        "flows": int(len(df)),
        "routing": {k: float((dec == k).mean()) for k in (AUTO_BENIGN, "auto_alert", REVIEW)},
        "labelled_flows": int(lab.sum()),
        "attacks": int(att.sum()), "benign": int(ben.sum()),
        "detection_rate": r((att & (dec != AUTO_BENIGN)).sum(), att.sum()),
        "attack_miss_rate": r((att & (dec == AUTO_BENIGN)).sum(), att.sum()),
        "false_alarm_rate": r((ben & (dec == "auto_alert")).sum(), ben.sum()),
        "benign_referral_rate": r((ben & (dec == REVIEW)).sum(), ben.sum()),
        "model_alone_detection_rate": r((att & (pred != "BENIGN")).sum(), att.sum()),
        "model_alone_false_alarm_rate": r((ben & (pred != "BENIGN")).sum(), ben.sum()),
        "exact_class_accuracy_known_classes": r(
            (lab & np.isin(truth, det.enc.classes) & (pred == truth)).sum(),
            (lab & np.isin(truth, det.enc.classes)).sum()),
        "per_label": {},
    }
    for label in pd.unique(truth[lab]):
        m = truth == label
        res["per_label"][label] = {
            "n": int(m.sum()), "known_class": label in det.enc.classes,
            "review": float((dec[m] == REVIEW).mean()), "auto_alert": float((dec[m] == "auto_alert").mean()),
            "auto_benign": float((dec[m] == AUTO_BENIGN).mean()),
            "top_predictions": pd.Series(pred[m]).value_counts(normalize=True).head(3).round(3).to_dict()}

    out = Path("reports/external")
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.csv).stem
    (out / f"{stem}.json").write_text(json.dumps(res, indent=2, default=str))

    pc = lambda x, d=2: "–" if x is None else f"{100 * x:.{d}f}%"  # noqa: E731
    lines = [f"# External data: {meta['file']}", "",
             f"Model bundle {det.version}. {res['flows']:,} flows "
             f"({'random sample of ' + format(meta['rows_in_file'], ',') if meta['sampled'] else 'all rows'}). "
             f"Measurements matched: {meta['features_found']}/{meta['features_total']}"
             + (f" (filled with typical values: {', '.join(meta['features_missing'])})" if meta['features_missing'] else "") + ".", "",
             "## Routing", "",
             f"- Auto-closed as normal: {pc(res['routing'][AUTO_BENIGN])}",
             f"- Confident alerts: {pc(res['routing']['auto_alert'])}",
             f"- Sent to a human: {pc(res['routing'][REVIEW])}", ""]
    if res["labelled_flows"]:
        lines += ["## Against the labels in the file", "",
                  "| | Deployed system (with review) | CNN-LSTM alone |", "|---|---|---|",
                  f"| Attacks caught (alerted or reviewed) | {pc(res['detection_rate'])} | {pc(res['model_alone_detection_rate'])} |",
                  f"| Attacks missed (closed as normal) | {pc(res['attack_miss_rate'])} | – |",
                  f"| False alarms on normal traffic | {pc(res['false_alarm_rate'], 3)} | {pc(res['model_alone_false_alarm_rate'], 3)} |",
                  f"| Normal traffic sent to review | {pc(res['benign_referral_rate'])} | – |",
                  f"| Exact-class accuracy (known classes) | {pc(res['exact_class_accuracy_known_classes'])} | |", "",
                  "## Per label", "", "| label | flows | known class? | review | alert | closed as normal | model's top guesses |",
                  "|---|---|---|---|---|---|---|"]
        for k, v in sorted(res["per_label"].items(), key=lambda kv: -kv[1]["n"]):
            guesses = ", ".join(f"{a} {100 * b:.0f}%" for a, b in v["top_predictions"].items())
            lines.append(f"| {k} | {v['n']:,} | {'yes' if v['known_class'] else '**no**'} | {pc(v['review'], 1)} | "
                         f"{pc(v['auto_alert'], 1)} | {pc(v['auto_benign'], 1)} | {guesses} |")
    (out / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
