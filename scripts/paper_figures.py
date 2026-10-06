"""Figures for the research paper (docs/paper/figs/*.pdf), from saved result files only.

Palette validated with the dataviz validator (blue / orange / aqua); every bar also
carries a hatch pattern and a value label so the figures survive greyscale printing.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

OUT = Path("docs/paper/figs")
SERIES = [  # (key in result json, legend label, colour, hatch)
    ("hybrid", "Hybrid (deployed)", "#2a78d6", ""),
    ("ours", "CNN-LSTM (entropy + distance)", "#eb6834", "///"),
    ("rf", "Random Forest alone", "#1baf7a", "..."),
]
INK, MUTED, GRID = "#1f1f1e", "#5f5e58", "#e4e3dc"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": INK, "axes.linewidth": 0.6,
    "hatch.linewidth": 0.5, "hatch.color": "white", "pdf.fonttype": 42,
})


def grouped_missed(names, values, path, xlabel):
    """values[series_key] = list of missed fractions, one per name."""
    fig, ax = plt.subplots(figsize=(3.45, 0.42 * len(names) + 0.9))
    h = 0.26
    y = np.arange(len(names))
    for i, (key, label, color, hatch) in enumerate(SERIES):
        v = 100 * np.array(values[key])
        pos = y + (i - 1) * (h + 0.02)
        ax.barh(pos, v, height=h, color=color, hatch=hatch, label=label,
                edgecolor="white", linewidth=0.8)
        for p, x in zip(pos, v):
            ax.text(x + 1.2, p, f"{x:.1f}", va="center", fontsize=6.2, color=INK)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xlabel(xlabel)
    ax.xaxis.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=2, frameon=False,
              fontsize=6.5, handlelength=1.6, columnspacing=1.0)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    loao = json.loads(Path("reports/generalisation/loao.json").read_text())
    names = list(loao)
    grouped_missed(names, {k: [loao[a][k]["auto_benign_missed"] for a in names]
                           for k, *_ in SERIES},
                   OUT / "loao_missed.pdf", "Unseen-attack flows auto-closed as benign (%)")

    day = json.loads(Path("reports/generalisation/day_split.json").read_text())
    cls = [c for c, r in day["per_class"].items() if not r["seen_in_training"]]
    grouped_missed(cls, {k: [day["per_class"][c][k]["auto_benign_missed"] for c in cls]
                         for k, *_ in SERIES},
                   OUT / "day_missed.pdf", "Attack flows auto-closed as benign (%)")
    print("written:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
