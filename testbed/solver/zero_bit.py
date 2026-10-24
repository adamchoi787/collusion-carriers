"""pi_0: the best collusive scheme that sends no bits before bidding.

A 0-bit scheme may use only what each firm knows on its own: its own cost on
the contract, the round and contract index, and its firm index. Expected
profit is computed exactly by enumerating every cost profile of one contract
(n_values^N profiles); contracts are independent, so the per-round value is K
times that. Schemes that treat firms asymmetrically rotate the roles by round
parity (and contract index), so every firm gets the same profit on average.

The searched family (every member bids the reserve r or abstains, unless
``bid_step`` is given):

``split(t)``
    Every firm bids r iff its cost <= t; ties split at random. t = r is the
    plan's k = 0 point. Own-cost participation thresholds.
``asym(t_1..t_N)``
    Firm in role i bids r iff its cost <= t_i; roles rotate with round parity.
    Includes pure rotation ("the designated firm bids r if its cost <= t,
    everyone else abstains") as t_others = cost_low - 1.
``priority(t_d, t_b)``  (needs ``bid_step``)
    Rotation with a backup: the designated firm bids r - bid_step if its cost
    <= t_d; the others bid r if their cost <= t_b. The designated firm wins
    whenever it bids.
``ladder(thresholds)``  (needs ``bid_step``)
    Bid shading as a simultaneous signal: a firm in cost bin l (l = 0 lowest)
    bids r - bid_step * (L - 1 - l); firms above the last threshold abstain.
    The lowest bid wins. With bid_step -> 0 this approaches pi_full, so a
    0-bit benchmark is only meaningful for a stated bid grid. The default
    (``bid_step=None``) excludes these, matching the plan's convention that
    winners are paid r.

Thresholds are searched over every value in {cost_low - 1 .. r}; a scheme is
reported with its parameters.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from .collusive import Market


@dataclass
class Scheme:
    name: str
    params: dict
    contract_value: float          # expected industry profit per contract
    per_firm_round: float = 0.0    # filled in by best_zero_bit
    notes: str = ""


def _profiles(m: Market) -> np.ndarray:
    sup = m.support
    return np.array(list(itertools.product(sup, repeat=m.n_firms)), dtype=float)


def _value_from_bids(costs: np.ndarray, bids: np.ndarray) -> float:
    """Expected industry profit: lowest bid wins (ties uniform), winner earns bid - cost.

    ``bids`` uses +inf for abstain. Each row is one equally likely cost profile."""
    low = bids.min(axis=1, keepdims=True)
    finite = np.isfinite(low[:, 0])
    winners = (bids == low) & finite[:, None]
    n_w = winners.sum(axis=1)
    margin = np.where(winners, bids - costs, 0.0).sum(axis=1)
    margin = np.divide(margin, n_w, out=np.zeros_like(margin), where=n_w > 0)
    return float(margin.mean())


def _thresholds(m: Market):
    return list(range(m.cost_low - 1, int(np.floor(m.reserve)) + 1))


def search_split(m: Market) -> Scheme:
    costs, r = _profiles(m), m.reserve
    best = None
    for t in _thresholds(m):
        bids = np.where(costs <= t, r, np.inf)
        v = _value_from_bids(costs, bids)
        if best is None or v > best.contract_value + 1e-12:
            best = Scheme("split", {"t": t}, v)
    return best


def search_asym(m: Market) -> Scheme:
    costs, r = _profiles(m), m.reserve
    best = None
    ts = _thresholds(m)
    for combo in itertools.combinations_with_replacement(ts[::-1], m.n_firms):
        # roles rotate, so only the multiset of thresholds matters
        t = np.array(combo, dtype=float)
        bids = np.where(costs <= t[None, :], r, np.inf)
        v = _value_from_bids(costs, bids)
        if best is None or v > best.contract_value + 1e-12:
            best = Scheme("asym", {"t": list(combo)}, v)
    return best


def search_rotation(m: Market) -> Scheme:
    """Pure rotation: the designated firm (round parity) bids r if cost <= t; others abstain."""
    costs, r = _profiles(m), m.reserve
    best = None
    for t in _thresholds(m):
        bids = np.full_like(costs, np.inf)
        bids[:, 0] = np.where(costs[:, 0] <= t, r, np.inf)
        v = _value_from_bids(costs, bids)
        if best is None or v > best.contract_value + 1e-12:
            best = Scheme("rotation", {"t": t}, v)
    return best


def search_priority(m: Market, bid_step: float) -> Scheme:
    costs, r = _profiles(m), m.reserve
    best = None
    for td, tb in itertools.product(_thresholds(m), repeat=2):
        bids = np.where(costs <= tb, r, np.inf)
        bids[:, 0] = np.where(costs[:, 0] <= td, r - bid_step, np.inf)
        v = _value_from_bids(costs, bids)
        if best is None or v > best.contract_value + 1e-12:
            best = Scheme("priority", {"t_designated": td, "t_backup": tb, "bid_step": bid_step}, v)
    return best


def search_ladder(m: Market, bid_step: float, max_levels: int = 3) -> Scheme:
    costs, r = _profiles(m), m.reserve
    best = None
    ts = _thresholds(m)
    for levels in range(2, max_levels + 1):
        # levels - 1 interior thresholds plus a participation cutoff
        for cuts in itertools.combinations(ts, levels):
            *inner, top = cuts
            level = np.zeros_like(costs)
            for t in inner:
                level += costs > t
            bids = r - bid_step * (levels - 1 - level)
            bids = np.where(costs <= top, bids, np.inf)
            v = _value_from_bids(costs, bids)
            if best is None or v > best.contract_value + 1e-12:
                best = Scheme("ladder", {"thresholds": list(inner), "cutoff": top,
                                         "levels": levels, "bid_step": bid_step}, v)
    return best


def best_zero_bit(m: Market, k_contracts: int, bid_step: float | None = None) -> tuple[Scheme, list[Scheme]]:
    """Search the family; return (winner, best member of each sub-family).

    Values are per firm per round: K * contract_value / N."""
    cands = [search_split(m), search_asym(m), search_rotation(m)]
    if bid_step is not None:
        cands += [search_priority(m, bid_step), search_ladder(m, bid_step)]
    for s in cands:
        s.per_firm_round = k_contracts * s.contract_value / m.n_firms
    winner = max(cands, key=lambda s: round(s.contract_value, 12))  # first (simplest) wins ties
    return winner, cands
