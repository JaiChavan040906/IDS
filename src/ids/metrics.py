"""One metrics function used by every model, so all numbers are comparable.

Multiclass: accuracy, macro / weighted precision-recall-F1, per-class scores.
Binary view (attack vs BENIGN, class index 0 = BENIGN): the numbers the paper
reports - accuracy, precision, detection rate (= recall), F1, FPR, FNR.
"""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix,
                             precision_recall_fscore_support)

BENIGN = 0


def compute_metrics(y_true, y_pred, classes, unreliable=()) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    labels = np.arange(len(classes))

    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels,
                                                 zero_division=0)
    mp, mr, mf, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels,
                                                    average="macro", zero_division=0)
    wf = precision_recall_fscore_support(y_true, y_pred, labels=labels,
                                         average="weighted", zero_division=0)[2]
    # Macro-F1 without the classes that are too small to trust.
    reliable = [i for i, c in enumerate(classes) if c not in unreliable]
    mf_rel = float(np.mean(f[reliable]))

    t_att, p_att = y_true != BENIGN, y_pred != BENIGN
    tp = int((t_att & p_att).sum()); fn = int((t_att & ~p_att).sum())
    fp = int((~t_att & p_att).sum()); tn = int((~t_att & ~p_att).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0

    return {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(mp),
        "macro_recall": float(mr),
        "macro_f1": float(mf),
        "macro_f1_reliable": mf_rel,
        "weighted_f1": float(wf),
        "binary": {
            "accuracy": (tp + tn) / len(y_true),
            "precision": prec,
            "detection_rate": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "fpr": fp / (fp + tn) if fp + tn else 0.0,
            "fnr": fn / (fn + tp) if fn + tp else 0.0,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        },
        "per_class": {
            c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]),
                "support": int(s[i]), "unreliable": c in unreliable}
            for i, c in enumerate(classes)
        },
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def save_metrics(metrics: dict, path: str | Path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(metrics, indent=2))


def plot_confusion(metrics: dict, classes, path: str | Path, title: str = ""):
    """Row-normalised confusion matrix (each row = where that true class went)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cm = np.array(metrics["confusion_matrix"], dtype=float)
    norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(classes)), classes, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(classes)), classes, fontsize=8)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j]:
                ax.text(j, i, f"{int(cm[i, j])}", ha="center", va="center", fontsize=6,
                        color="white" if norm[i, j] > 0.5 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046, label="Row fraction (recall)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
