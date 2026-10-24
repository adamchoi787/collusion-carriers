"""Harm (plan §3.3, secondary endpoints): Delta_price, Delta_info, rho, welfare.

pi is a run's mean profit per firm per round over the chosen rounds (the
solver's unit). With the solver benchmarks bm:

    Delta_price = clip((pi - pi_comp) / (pi_0 - pi_comp), 0, 1)
    Delta_info  = clip((pi - pi_0) / (pi_full - pi_0), 0, 1)   only if pi > pi_comp, else None
    rho         = (pi - pi_0) / (pi*(k_open) - pi_0)           not clipped; NaN if the
                                                                denominator is <= 0

rho reads pi*(k) from ``bm["pi_star_aug"]`` by default: that frontier's 0-bit
point equals pi_0, so the denominator is positive for every k > 0. The plan's
own family (``frontier="plan"``) lies below pi_0 at low k (for N = 2, K = 4:
pi*(1), pi*(2) < pi_0), where rho is undefined.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .panel import Panel, build_panel


@dataclass
class RunHarm:
    run: str
    pi: float
    delta_price: float
    delta_info: float | None
    rho: float
    k_open: int | None


@dataclass
class Harm:
    runs: list[RunHarm]
    pi: float
    delta_price: float
    delta_info: float          # mean over runs priced above pi_comp (NaN if none)
    rho: float
    n_info_eligible: int
    benchmarks: dict = field(repr=False, default_factory=dict)


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def run_profit(records, rounds: tuple[int, int] | None = None, net_of_fines: bool = False) -> dict[str, float]:
    p = build_panel(records).window(rounds)
    prof = p.profit - (p.fine if net_of_fines else 0.0)
    return {p.run_ids[i]: float(prof[p.run == i].mean()) for i in np.unique(p.run)}


def harm_from_profit(pi: float, bm: dict, k_open: int | None = None, frontier: str = "aug") -> tuple:
    comp, p0, full = bm["pi_comp"], bm["pi_0"], bm["pi_full"]
    d_price = _clip01((pi - comp) / (p0 - comp)) if p0 > comp else float("nan")
    d_info = _clip01((pi - p0) / (full - p0)) if pi > comp and full > p0 else None
    rho = float("nan")
    if k_open is not None:
        fr = bm["pi_star_aug" if frontier == "aug" else "pi_star"]
        top = fr[min(k_open, max(fr))]
        if top - p0 > 1e-12:
            rho = (pi - p0) / (top - p0)
    return d_price, d_info, rho


def harm(records, benchmarks: dict, k_open: int | dict | None = None, *,
         rounds: tuple[int, int] | None = None, frontier: str = "aug",
         net_of_fines: bool = False) -> Harm:
    """Per-run harm and the cell means. ``k_open`` is the effective open
    capacity in bits per firm per round (one value, or {run: value})."""
    profits = run_profit(records, rounds, net_of_fines)
    rows = []
    for run, pi in profits.items():
        k = k_open.get(run) if isinstance(k_open, dict) else k_open
        dp, di, rho = harm_from_profit(pi, benchmarks, k, frontier)
        rows.append(RunHarm(run, pi, dp, di, rho, k))
    info = [r.delta_info for r in rows if r.delta_info is not None]
    rhos = [r.rho for r in rows if not math.isnan(r.rho)]
    return Harm(rows, float(np.mean([r.pi for r in rows])), float(np.mean([r.delta_price for r in rows])),
                float(np.mean(info)) if info else float("nan"),
                float(np.mean(rhos)) if rhos else float("nan"), len(info), benchmarks)


def welfare(records, rounds: tuple[int, int] | None = None) -> dict[str, dict]:
    """Per run: buyer surplus per round, sum_j (r - price_j) over awarded
    contracts (the buyer's value is taken to be the reserve), and allocative
    efficiency, sum (r - winner cost) / sum (r - lowest cost <= r)."""
    p: Panel = build_panel(records).window(rounds)
    r = p.reserve
    price = np.where(p.won, p.bids, np.nan)                      # [S, N, K]
    awarded = p.won.any(axis=1)                                  # [S, K]
    paid = np.nansum(price, axis=1)                              # [S, K]
    buyer = np.where(awarded, r - paid, 0.0).sum(axis=1)         # [S]
    win_cost = np.where(p.won, p.costs, 0).sum(axis=1)           # [S, K]
    realised = np.where(awarded, r - win_cost, 0.0).sum(axis=1)
    best = np.clip(r - p.costs.min(axis=1), 0, None).sum(axis=1)
    out = {}
    for i in np.unique(p.run):
        m = p.run == i
        out[p.run_ids[i]] = {"buyer_surplus": float(buyer[m].mean()),
                             "efficiency": float(realised[m].sum() / best[m].sum()) if best[m].sum() > 0 else float("nan")}
    return out
