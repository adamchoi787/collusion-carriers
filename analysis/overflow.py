"""Context overflow on the open-weight servers, and a pre-overflow sensitivity window.

    python analysis/overflow.py runs/

The vLLM servers cap a prompt at 65,536 tokens. Each firm keeps its whole conversation, so in
long games a turn can overflow late in the run. That turn falls back as the pre-registration
specifies (pre-bid steps follow the guideline; no bids are placed), and the firm earns nothing
that round. Chat makes prompts longest, so s5-open is hit most, and this biases H5.3 (open vs
close) against open. Fallbacks stay in the primary analysis, as pre-registered. This script
reports:

  overflow  per model and cell: firm-rounds in rounds 51-100 that fell back on an overflow,
            and the earliest round at which any did
  window    H5.2 and H5.3 (exact sign-flip, paired by seed) on rounds 51 to the round before
            the first overflow in any game of that model, where every cell is clean
  table     the paper's per-seed appendix rows for models that overflowed (profit per cell,
            including s5-close-coded where run; private_message attempts; overflow open/close)
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.coded_control import rounds  # noqa: E402
from analysis.study5 import CELLS, WINDOW, load, model_of, profit, sign_flip_p  # noqa: E402

OVERFLOW = "reduce the length of the input prompt"


def overflowed(r: dict) -> bool:
    u = r.get("usage") or {}
    return OVERFLOW in str(u)


def table_rows(runs_dir: str, model: str, seeds: dict[int, dict[str, list[dict]]]) -> list[str]:
    short = model.split("/")[-1]
    out = []
    for s in sorted(seeds):
        c = seeds[s]
        coded = rounds(runs_dir, "s5-close-coded", s)
        pm = sum(1 for r in c["s5-close-decoy"] if r["round"] > 40
                 for m in (r.get("messages_sent") or []) if m.get("channel") == "private_message")
        ov = [sum(overflowed(r) for r in c[cell] if WINDOW[0] <= r["round"] <= WINDOW[1]) for cell in ("s5-open", "s5-close")]
        cells = " | ".join(f"{profit(c[cell]):.2f}" for cell in CELLS)
        out.append(f"| {s} | {short} | {cells} | {f'{profit(coded):.2f}' if coded else '–'} | {pm} | {ov[0]} / {ov[1]} |")
    return out


def main(runs_dir: str) -> None:
    rows = []
    data = load(runs_dir)
    by_model: dict[str, dict[int, dict[str, list[dict]]]] = defaultdict(lambda: defaultdict(dict))
    for cell in CELLS:
        for seed, recs in data[cell].items():
            by_model[model_of(recs)][seed][cell] = recs
    for model, seeds in sorted(by_model.items()):
        seeds = {s: c for s, c in seeds.items() if len(c) == len(CELLS)}
        if not seeds:
            continue
        first = min((r["round"] for c in seeds.values() for recs in c.values() for r in recs
                     if WINDOW[0] <= r["round"] and overflowed(r)), default=None)
        print(f"{model}: seeds {sorted(seeds)}")
        for cell in CELLS:
            n = [sum(overflowed(r) for r in seeds[s][cell] if WINDOW[0] <= r["round"] <= WINDOW[1]) for s in sorted(seeds)]
            print(f"  {cell:15s} overflow fallbacks per seed (of 100 firm-rounds): {n}")
        if first is None:
            print("  no overflow; the pre-registered window is clean")
            continue
        rows += table_rows(runs_dir, model, seeds)
        hi = first - 1
        print(f"  first overflow at round {first}; sensitivity window rounds {WINDOW[0]}-{hi}")

        def prof(recs: list[dict]) -> float:
            return float(np.mean([r["profit"] for r in recs if WINDOW[0] <= r["round"] <= hi]))
        p = {s: {cell: prof(seeds[s][cell]) for cell in CELLS} for s in sorted(seeds)}
        for cell in CELLS:
            v = [p[s][cell] for s in p]
            print(f"    {cell:15s} profit {np.mean(v):.2f} ± {np.std(v, ddof=1) if len(v) > 1 else 0:.2f}")
        for name, a, b in (("H5.2 close - dark", "s5-close", "s5-close-dark"), ("H5.3 open - close", "s5-open", "s5-close")):
            d = [p[s][a] - p[s][b] for s in p]
            print(f"    {name}: mean {np.mean(d):+.3f}, one-sided sign-flip p = {sign_flip_p(d):.4f} (n = {len(d)})")
    print("\nper-seed table (paper appendix B.4):")
    print("\n".join(rows))


if __name__ == "__main__":
    main(sys.argv[1])
