"""The open-weight arm's pre-registered gate (plan/preregistration.md, Addendum A).

    python analysis/gate_ow.py runs/ 401-420 501-520

For each seed range: pooled total leakage I(c_A; b_B | H) over that model's Study 5 formation
games, rounds 21-40, against the exact within-run permutation null (999 permutations). A model
passes when p < 0.05: its chat carries cost information, so there is a coalition to close.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from testbed.metrics import build_panel, total_leakage  # noqa: E402
from testbed.metrics.io import load_run  # noqa: E402

WINDOW = (21, 40)
ALPHA = 0.05


def gate(runs_dir: str, seeds: list[int]) -> dict:
    recs, done = [], []
    for s in seeds:
        log = Path(runs_dir, "s5-formation", f"{s}.jsonl")
        rows = [r for r in load_run(log) if r.get("type") == "round"] if log.exists() else []
        if rows and max(r["round"] for r in rows) >= WINDOW[1]:
            recs += [dict(r, run=f"f/{s}") for r in rows]
            done.append(s)
    tl = total_leakage(build_panel(recs), rounds=WINDOW, n_perm=999)
    return {"seeds": done, "bits": tl.bits, "p": tl.p_value, "passes": tl.p_value < ALPHA}


def main(runs_dir: str, *ranges: str) -> None:
    for rng in ranges:
        lo, hi = map(int, rng.split("-"))
        g = gate(runs_dir, list(range(lo, hi + 1)))
        print(f"seeds {rng}: {len(g['seeds'])} complete formations, leakage {g['bits']:.3f} bits, "
              f"p = {g['p']:.4f} -> {'PASS' if g['passes'] else 'FAIL'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
