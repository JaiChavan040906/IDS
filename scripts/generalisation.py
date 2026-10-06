"""Evaluation steps 5-6: unseen attacks and unseen days.

loao  - leave-one-attack-out: remove attack A from training, then ask what
        happens to A's flows. Success for a HITL system = A is sent to review
        or still raised as SOME attack; failure = A is auto-closed as benign.
days  - train on earlier days, evaluate on later days (most of their attacks
        are new types). Binary view: is attack traffic caught or referred?

Both compare our CNN-LSTM + routing against a Random Forest, whose own
confidence (1 - max prob) is used for referral at the same referral budget.

Usage:
    .venv/Scripts/python scripts/generalisation.py loao
    .venv/Scripts/python scripts/generalisation.py days
"""

import argparse
import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from ids.data import LABEL_COL, load_config, load_split
from ids.nn import predict, train
from ids.preprocessing import LabelEncoder, Preprocessor
from ids.uncertainty import (AUTO_ALERT, AUTO_BENIGN, REVIEW, fit_uncertainty,
                             mahalanobis_sample, normalized_entropy, route, second_opinion,
                             softmax)

UCFG = yaml.safe_load(open("configs/uncertainty.yaml", encoding="utf-8"))


def outcome(decision):
    n = max(len(decision), 1)
    return {"n": int(len(decision)),
            "review": float((decision == REVIEW).sum() / n),
            "auto_alert": float((decision == AUTO_ALERT).sum() / n),
            "auto_benign_missed": float((decision == AUTO_BENIGN).sum() / n)}


def free_memory():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_ours(X, y, Xcal, ycal, K, cfg, seed):
    """Train CNN-LSTM, fit calibration + thresholds. Returns a scoring function."""
    model, _ = train(X, y, Xcal, ycal, K, cfg["train"], seed)
    idx = mahalanobis_sample(y, UCFG["mahalanobis_train_rows"], seed)
    _, emb_tr = predict(model, X[idx], with_embeddings=True)
    logits_c, emb_c = predict(model, Xcal, with_embeddings=True)
    T, ood, th = fit_uncertainty(emb_tr, y[idx], logits_c, emb_c, ycal, K, UCFG)
    del emb_tr, emb_c, logits_c

    def score(Xe):
        logits, emb = predict(model, Xe, with_embeddings=True)
        p = softmax(logits, T)
        pred, ent, dist = p.argmax(1), normalized_entropy(p), ood.score(emb)
        return {"pred": pred, "ent": ent, "dist": dist, "th": th,
                "both": route(pred, ent, dist, th["entropy"], th["distance"]),
                "entropy_only": route(pred, ent, np.zeros_like(ent), th["entropy"], np.inf)}
    return score


def run_rf(X, y, Xcal, cfg, seed):
    rf = RandomForestClassifier(random_state=seed, **cfg["rf"]).fit(X, y)
    unc_cal = 1 - rf.predict_proba(Xcal).max(1)
    # RF alone: same referral budget as ours (most uncertain 1% of calibration flows)
    tau = np.quantile(unc_cal, 1 - UCFG["entropy_referral_rate"])
    # RF as second opinion in the hybrid: its own budget (configs/uncertainty.yaml)
    tau_so = np.quantile(unc_cal, 1 - UCFG["rf_referral_rate"])

    def score(Xe):
        p = rf.predict_proba(Xe)
        pred = rf.classes_[p.argmax(1)]
        unsure = (1 - p.max(1)) > tau
        dec = np.where(pred == 0, AUTO_BENIGN, AUTO_ALERT).astype(object)
        dec[unsure] = REVIEW
        return {"pred": pred, "rf": dec, "probs": p, "classes": rf.classes_, "tau_so": tau_so}
    return score


def hybrid(s, r):
    """Deployed routing: CNN-LSTM signals OR the RF second opinion (unsure / disagrees)."""
    so = second_opinion(r["probs"], r["classes"], s["pred"], r["tau_so"])
    return route(s["pred"], s["ent"], s["dist"], s["th"]["entropy"], s["th"]["distance"],
                 extra_unsure=so["mask"])


def load_all():
    dcfg = load_config()
    art = Path(dcfg["artifact_dir"])
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    tr, va = load_split("train", dcfg), load_split("val", dcfg)
    return pre, enc, tr, va


def loao(cfg):
    pre, enc, tr, va = load_all()
    X, y = pre.transform(tr), enc.encode(tr[LABEL_COL])
    Xv, yv = pre.transform(va), enc.encode(va[LABEL_COL])
    del tr, va
    ia, ib = train_test_split(np.arange(len(yv)), train_size=UCFG["calibration_fraction"],
                              stratify=yv, random_state=UCFG["seed"])
    K = len(enc.classes)
    out_dir = Path(cfg["report_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    f = out_dir / "loao.json"
    if f.exists():
        results = json.loads(f.read_text())

    for attack in cfg["held_out_attacks"]:
        if attack in results:
            print(f"skip {attack} (done)")
            continue
        a = enc.index[attack]
        print(f"\n=== held out: {attack} ===", flush=True)
        keep_tr, keep_a, keep_b = y != a, yv[ia] != a, yv[ib] != a
        # the unseen attack's flows: all train + val rows of that class (never trained on)
        X_unseen = np.concatenate([X[y == a], Xv[yv == a]])
        Xcal, ycal = Xv[ia][keep_a], yv[ia][keep_a]
        Xin, yin = Xv[ib][keep_b], yv[ib][keep_b]

        ours = run_ours(X[keep_tr], y[keep_tr], Xcal, ycal, K, cfg, cfg["seed"])
        rf = run_rf(X[keep_tr], y[keep_tr], Xcal, cfg, cfg["seed"])
        s_u, r_u = ours(X_unseen), rf(X_unseen)
        s_in, r_in = ours(Xin), rf(Xin)
        results[attack] = {
            "n_unseen": int(len(X_unseen)),
            "hybrid": outcome(hybrid(s_u, r_u)),
            "ours": outcome(s_u["both"]),
            "ours_entropy_only": outcome(s_u["entropy_only"]),
            "rf": outcome(r_u["rf"]),
            "ours_predicted_as": pd.Series(np.array(enc.classes)[s_u["pred"]]).value_counts(
                normalize=True).round(4).head(4).to_dict(),
            "in_distribution_referral": {"hybrid": outcome(hybrid(s_in, r_in))["review"],
                                         "ours": outcome(s_in["both"])["review"],
                                         "rf": outcome(r_in["rf"])["review"]},
            "in_distribution_accuracy": {"ours": float((s_in["pred"] == yin).mean()),
                                         "rf": float((r_in["pred"] == yin).mean())},
        }
        print(json.dumps(results[attack], indent=1), flush=True)
        f.write_text(json.dumps(results, indent=2))
        # free this attack's models before the next one (7.7 GB RAM machine)
        del ours, rf, s_u, r_u, s_in, r_in, X_unseen, Xcal, ycal, Xin, yin
        free_memory()
    write_loao_md(results, out_dir)


def write_loao_md(results, out_dir):
    lines = ["# Leave-one-attack-out (unseen attack handling)", "",
             "Each row: the model was trained WITHOUT that attack. Shares of the unseen attack's flows.",
             "Success = sent to review or raised as some attack. Failure = auto-closed as benign.", "",
             "Missed = share of the unseen attack's flows auto-closed as benign (lower is better).", "",
             "| held-out attack | n | **hybrid (deployed)** | CNN-LSTM (entropy + distance) | "
             "CNN-LSTM (entropy only) | RF alone | hybrid: review / auto-alert | "
             "normal-traffic referral hybrid / CNN-LSTM / RF |",
             "|---|---|---|---|---|---|---|---|"]
    for a, r in results.items():
        h, o, e, f = r["hybrid"], r["ours"], r["ours_entropy_only"], r["rf"]
        ref = r["in_distribution_referral"]
        lines.append(
            f"| {a} | {r['n_unseen']:,} | **{100 * h['auto_benign_missed']:.1f}%** | "
            f"{100 * o['auto_benign_missed']:.1f}% | {100 * e['auto_benign_missed']:.1f}% | "
            f"{100 * f['auto_benign_missed']:.1f}% | "
            f"{100 * h['review']:.1f}% / {100 * h['auto_alert']:.1f}% | "
            f"{100 * ref['hybrid']:.2f}% / {100 * ref['ours']:.2f}% / {100 * ref['rf']:.2f}% |")
    (out_dir / "loao.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def days(cfg):
    pre, enc, tr, va = load_all()
    ds = cfg["day_split"]
    K = len(enc.classes)

    def part(df, days_):
        d = df[df["day"].astype(str).isin(days_)]
        return pre.transform(d), enc.encode(d[LABEL_COL])

    X, y = part(tr, ds["train_days"])
    Xcal, ycal = part(va, ds["train_days"])
    # evaluation: every non-test row of the later days (none were trained on)
    Xe = np.concatenate([part(tr, ds["test_days"])[0], part(va, ds["test_days"])[0]])
    ye = np.concatenate([part(tr, ds["test_days"])[1], part(va, ds["test_days"])[1]])
    del tr, va
    seen = set(np.unique(y))
    print(f"train {len(y):,} rows ({ds['train_days']}), evaluate {len(ye):,} rows ({ds['test_days']})")

    ours = run_ours(X, y, Xcal, ycal, K, cfg, cfg["seed"])(Xe)
    free_memory()
    rf = run_rf(X, y, Xcal, cfg, cfg["seed"])(Xe)
    hyb = hybrid(ours, rf)

    def binary(dec):
        att = ye != 0
        flagged = dec != AUTO_BENIGN          # alert OR review = a human/alert sees it
        return {"attack_caught_or_referred": float(flagged[att].mean()),
                "attack_missed": float((~flagged[att]).mean()),
                "benign_auto_closed": float((dec[~att] == AUTO_BENIGN).mean()),
                "benign_false_alert": float((dec[~att] == AUTO_ALERT).mean()),
                "benign_referred": float((dec[~att] == REVIEW).mean()),
                "overall_referral": float((dec == REVIEW).mean())}

    per_class = {}
    for c in np.unique(ye):
        m = ye == c
        per_class[enc.classes[c]] = {"n": int(m.sum()), "seen_in_training": bool(c in seen),
                                     "hybrid": outcome(hyb[m]), "ours": outcome(ours["both"][m]),
                                     "rf": outcome(rf["rf"][m])}
    res = {"train_days": ds["train_days"], "test_days": ds["test_days"],
           "hybrid": binary(hyb), "ours": binary(ours["both"]),
           "ours_entropy_only": binary(ours["entropy_only"]),
           "rf": binary(rf["rf"]), "per_class": per_class}
    out = Path(cfg["report_dir"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "day_split.json").write_text(json.dumps(res, indent=2))

    lines = [f"# Day-based split: train {', '.join(ds['train_days'])} -> "
             f"evaluate {', '.join(ds['test_days'])}", "",
             "| | **hybrid (deployed)** | CNN-LSTM (entropy + distance) | CNN-LSTM (entropy only) | RF alone |",
             "|---|---|---|---|---|"]
    for k in res["ours"]:
        lines.append(f"| {k} | **{100 * res['hybrid'][k]:.2f}%** | {100 * res['ours'][k]:.2f}% | "
                     f"{100 * res['ours_entropy_only'][k]:.2f}% | {100 * res['rf'][k]:.2f}% |")
    lines += ["", "## Per class (share missed = auto-closed as benign)", "",
              "| class | n | seen in training? | hybrid: missed | CNN-LSTM: missed | RF: missed |",
              "|---|---|---|---|---|---|"]
    for c, r in per_class.items():
        lines.append(f"| {c} | {r['n']:,} | {'yes' if r['seen_in_training'] else '**no**'} | "
                     f"**{100 * r['hybrid']['auto_benign_missed']:.1f}%** | "
                     f"{100 * r['ours']['auto_benign_missed']:.1f}% | "
                     f"{100 * r['rf']['auto_benign_missed']:.1f}% |")
    (out / "day_split.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", choices=["loao", "days"])
    args = ap.parse_args()
    cfg = yaml.safe_load(open("configs/generalisation.yaml", encoding="utf-8"))
    {"loao": loao, "days": days}[args.experiment](cfg)
