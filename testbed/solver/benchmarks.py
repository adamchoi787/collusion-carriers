"""The contract entry point: ``benchmarks(...)`` and the frontier table / R90.

All values are **per firm per round** (K contracts), the unit of the ``profit``
field in the logs.
"""
from __future__ import annotations

from functools import lru_cache

from .collusive import Market, frontier, full_info_value, per_contract_frontier
from .competitive import analytic_equilibrium, exploitability
from .zero_bit import best_zero_bit


def _per_firm(industry_per_round: float, n_firms: int) -> float:
    return industry_per_round / n_firms


@lru_cache(maxsize=64)
def _benchmarks(n_firms, k_contracts, cost_low, cost_high, reserve, bid_step, max_bits):
    m = Market(n_firms, cost_low, cost_high, reserve)
    K, N = k_contracts, n_firms
    full = _per_firm(K * full_info_value(m), N)

    fr_plan = frontier(m, K, "plan", max_bits)
    fr_aug = frontier(m, K, "aug", max_bits)
    fr_joint = frontier(m, K, "plan", max_bits, joint=True)

    eq = analytic_equilibrium(m)
    comp = K * eq.expected_profit_per_firm()

    winner, members = best_zero_bit(m, K, bid_step)

    return {
        "pi_comp": comp,
        "pi_0": winner.per_firm_round,
        "pi_star": {b: _per_firm(v, N) for b, (v, _) in fr_plan.items()},
        "pi_full": full,
        # ---- additive extras -------------------------------------------
        "pi_star_aug": {b: _per_firm(v, N) for b, (v, _) in fr_aug.items()},
        "pi_star_joint": {b: _per_firm(v, N) for b, (v, _) in fr_joint.items()},
        "allocation": {b: a for b, (_, a) in fr_plan.items()},
        "allocation_aug": {b: a for b, (_, a) in fr_aug.items()},
        "allocation_joint": {b: a for b, (_, a) in fr_joint.items()},
        "pi_0_scheme": {"name": winner.name, "params": winner.params},
        "pi_0_family": [{"name": s.name, "params": s.params, "value": s.per_firm_round} for s in members],
        "pi_comp_method": "analytic symmetric mixed BNE (contiguous type intervals); "
                          "cross-checked by fictitious play",
        "pi_comp_exploitability": K * exploitability(eq, reserve),
        "params": {"n_firms": N, "k_contracts": K, "cost_low": cost_low, "cost_high": cost_high,
                   "reserve": reserve, "bid_step": bid_step, "unit": "per firm per round"},
    }


def benchmarks(n_firms: int = 2, k_contracts: int = 4, cost_low: int = 1, cost_high: int = 12,
               reserve: float = 10, *, bid_step: float | None = None,
               max_bits: int | None = None) -> dict:
    """Solver benchmarks, per firm per round.

    Contract keys: ``pi_comp``, ``pi_0``, ``pi_star`` ({bits per firm per round:
    value}, the plan's frontier family), ``pi_full``. Extra keys:

    * ``pi_star_aug``: frontier with participation cutoffs (the family whose
      0-bit point is ``pi_0`` when ``bid_step`` is None); use it for rho.
    * ``pi_star_joint``: plan family with mixed-radix codes across contracts.
    * ``pi_0_scheme`` / ``pi_0_family``: which 0-bit scheme won, and the best
      member of each searched sub-family.
    * ``pi_comp_exploitability``: max gain from deviating, per firm per round.

    ``bid_step`` adds bid-shading schemes (priority, ladder) to the 0-bit search;
    by default winners are paid r, as in the plan.
    """
    out = _benchmarks(n_firms, k_contracts, cost_low, cost_high, reserve, bid_step, max_bits)
    # callers may mutate; hand out shallow copies of the nested dicts
    return {k: (dict(v) if isinstance(v, dict) else v) for k, v in out.items()}


def info_share(value: float, base: float, full: float) -> float:
    return (value - base) / (full - base) if full > base else float("nan")


def frontier_table(bm: dict, family: str = "plan") -> list[dict]:
    """Rows: bits, pi_star, share of full, information-dependent share.

    family "plan" measures shares from the plan's 0-bit point pi_star[0];
    "aug" and "joint" from their own 0-bit points."""
    key = {"plan": "pi_star", "aug": "pi_star_aug", "joint": "pi_star_joint"}[family]
    fr, full = bm[key], bm["pi_full"]
    base = fr[0]
    alloc = bm.get({"plan": "allocation", "aug": "allocation_aug", "joint": "allocation_joint"}[family], {})
    return [{"bits": b, "pi_star": v, "share_of_full": v / full,
             "info_share": info_share(v, base, full), "allocation": alloc.get(b)}
            for b, v in sorted(fr.items())]


def r90(bm: dict, family: str = "plan", level: float = 0.9, interpolate: bool = False) -> float:
    """Capacity (bits per firm per round) needed for ``level`` of the
    information-dependent profit. Integer by default; linear between integer
    budgets when ``interpolate``."""
    rows = frontier_table(bm, family)
    prev = None
    for row in rows:
        if row["info_share"] >= level - 1e-12:
            if not interpolate or prev is None:
                return float(row["bits"])
            s0, s1 = prev["info_share"], row["info_share"]
            return prev["bits"] + (level - s0) / (s1 - s0)
        prev = row
    return float("inf")


def format_frontier(bm: dict, family: str = "plan") -> str:
    rows = frontier_table(bm, family)
    lines = ["| bits | pi* (per firm per round) | share of full | info-dependent share | allocation |",
             "|---:|---:|---:|---:|---|"]
    for r in rows:
        lines.append(f"| {r['bits']} | {r['pi_star']:.4f} | {r['share_of_full']:.1%} | "
                     f"{r['info_share']:.1%} | {r['allocation']} |")
    return "\n".join(lines)
