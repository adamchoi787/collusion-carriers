"""Paper figures for Study 5, regenerated from raw logs.

    python analysis/figures.py runs/ paper/figures/

fig2_profit.png    profit per firm per round in each cell, one line per seed (paired), per model,
                   against the competitive and 0-bit benchmarks.
fig1_leakage.png   total leakage I(c_A;b_B|H) per cell, pooled over a model's seeds: words carry
                   cost information while chat is open; nothing does once it closes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.study5 import CELLS, WINDOW, load, model_of, profit  # noqa: E402
from testbed.metrics import build_panel, total_leakage  # noqa: E402
from testbed.metrics.io import load_run  # noqa: E402
from testbed.solver import benchmarks  # noqa: E402

LABELS = {"s5-open": "open", "s5-close": "close", "s5-close-decoy": "close-\ndecoy", "s5-close-dark": "close-\ndark"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # reference categorical slots 1-4 (adjacent bars)
ORDER = ["gpt-6-luna", "claude-haiku-5-5", "Qwen/Qwen3.8-27B-FP8", "google/gemma-4-26B-A4B-it"]
SHORT = {"Qwen/Qwen3.8-27B-FP8": "Qwen3.8-27B", "google/gemma-4-26B-A4B-it": "Gemma-4-26B-A4B"}
FORMATION_WINDOW = (21, 40)


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def by_model(data):
    seeds = sorted(set.intersection(*(set(data[c]) for c in CELLS)))
    out: dict[str, list[int]] = {}
    for s in seeds:
        out.setdefault(model_of(data["s5-close"][s]), []).append(s)
    return {m: out[m] for m in sorted(out, key=lambda m: ORDER.index(m) if m in ORDER else 99)}


def fig_profit(data, models, path):
    bm = benchmarks(2, 4, 1, 12, 10)
    cols = min(len(models), 2)
    rows = -(-len(models) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(3.6 * cols, 2.9 * rows), sharey=True, squeeze=False)
    axes = list(axes.flat)
    x = range(len(CELLS))
    for ax, (model, seeds), color in zip(axes, models.items(), SERIES):
        for s in seeds:
            ax.plot(x, [profit(data[c][s]) for c in CELLS], color=color, lw=1.2, alpha=0.55,
                    marker="o", ms=4, mec="white", mew=0.8)
        mean = [sum(profit(data[c][s]) for s in seeds) / len(seeds) for c in CELLS]
        ax.plot(x, mean, color=INK, lw=2, marker="D", ms=5, mec="white", mew=1, label="mean")
        for y, name in ((bm["pi_0"], "0-bit\nbenchmark"), (bm["pi_comp"], "competitive")):
            ax.axhline(y, color=MUTED, lw=0.9, ls="--")
            if ax in axes[cols - 1::cols]:
                ax.text(1.02, y, name, color=MUTED, fontsize=7, va="center", transform=ax.get_yaxis_transform())
        ax.set_xticks(list(x), [LABELS[c] for c in CELLS], fontsize=8)
        ax.set_title(f"{SHORT.get(model, model)} ({len(seeds)} seeds)", fontsize=9, color=INK)
        _style(ax)
    for ax in axes[::cols]:
        ax.set_ylabel(f"profit per firm per round\n(rounds {WINDOW[0]}–{WINDOW[1]})", fontsize=8, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def fig_leakage(data, models, formation_dir, path):
    cols = ["formation"] + list(CELLS)
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    width = 0.8 / len(models)
    for k, ((model, seeds), color) in enumerate(zip(models.items(), SERIES)):
        vals, ps = [], []
        for c in cols:
            if c == "formation":
                recs = [dict(r, run=f"f/{s}") for s in seeds
                        for r in load_run(Path(formation_dir, f"{s}.jsonl")) if r.get("type") == "round"]
                win = FORMATION_WINDOW
            else:
                recs = [dict(r, run=f"{c}/{s}") for s in seeds for r in data[c][s]]
                win = WINDOW
            tl = total_leakage(build_panel(recs), rounds=win, n_perm=999)
            vals.append(tl.bits)
            ps.append(tl.p_value)
        xs = [i + (k - (len(models) - 1) / 2) * width for i in range(len(cols))]
        ax.bar(xs, vals, width=width - 0.03, color=color, label=SHORT.get(model, model))
        for xi, v, p in zip(xs, vals, ps):
            if p < 0.05:
                ax.text(xi, v + 0.02, "*", ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(cols)), ["formation\n(chat, r21–40)"] + [LABELS[c].replace("\n", "") for c in CELLS],
                  fontsize=8)
    ax.set_ylabel("total leakage I(c_A; b_B | H), bits", fontsize=8, color=INK)
    ax.legend(frameon=False, fontsize=8)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def main(runs_dir: str, out_dir: str) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    data = load(runs_dir)
    models = by_model(data)
    fig_profit(data, models, Path(out_dir, "fig2_profit.png"))
    fig_leakage(data, models, Path(runs_dir, "s5-formation"), Path(out_dir, "fig1_leakage.png"))
    print("wrote", sorted(p.name for p in Path(out_dir).glob("fig*.png")))


if __name__ == "__main__":
    main(*(sys.argv[1:3] if len(sys.argv) > 2 else ("runs", "paper/figures")))
