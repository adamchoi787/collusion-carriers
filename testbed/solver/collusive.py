"""k-bit collusive schemes: the rate-profit frontier pi*(k).

Model (plan §1, generalising analysis/frontier.py to N firms). For each of K
independent contracts, every firm draws a private cost uniform on
{cost_low..cost_high}. A k-bit scheme on one contract: every firm announces its
cost bin (2^k bins, monotone thresholds shared by all firms); the firms in the
lowest announced bin take the contract at the reserve price r, ties split at
random. Firms whose cost exceeds r never take a contract.

A per-firm budget of b bits per round is shared across the K contracts; profit
is additive across contracts, so the best allocation is a knapsack over integer
bits per contract.

Two scheme families are solved:

* ``"plan"``: exactly the plan's frontier (and analysis/frontier.py): every
  firm in the lowest bin with cost <= r bids r.
* ``"aug"`` (participation-augmented): the same announcement, but the bid stage
  is also used as a simultaneous yes/no signal. A firm alone in the lowest bin
  bids r if its cost is <= r; firms that tie in the lowest bin bid r only if
  their cost is <= t_j, where the cutoff t_j may depend on how many firms tied
  (announcements are public). With one bin (k = 0) nobody knows j, so a single
  cutoff applies: this is the best symmetric 0-bit scheme of zero_bit.py.
  The plan family is the special case t_j = r. See README.md for why this
  matters: the plan family's frontier lies *below* the best 0-bit scheme at
  low k.

Per-contract expected industry profit decomposes over bins: a bin S
contributes only when it is the lowest occupied bin, and that event depends
only on S's own bounds. So the optimal partition into at most m contiguous bins
is an exact dynamic programme over the sorted cost support.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

FAMILIES = ("plan", "aug")


@dataclass(frozen=True)
class Market:
    n_firms: int = 2
    cost_low: int = 1
    cost_high: int = 12
    reserve: float = 10

    @property
    def support(self) -> np.ndarray:
        return np.arange(self.cost_low, self.cost_high + 1)

    @property
    def n_values(self) -> int:
        return self.cost_high - self.cost_low + 1


def _tied_value(costs: np.ndarray, reserve: float, j: int, cutoff: float) -> float:
    """Expected industry profit when j firms tie in a bin with cost values
    ``costs`` (equally likely) and participate iff cost <= cutoff (and <= r).
    The winner is uniform among participants, so given at least one
    participant the expected margin is E[r - c | c in bin, c <= cutoff]."""
    part = costs[(costs <= cutoff) & (costs <= reserve)]
    if part.size == 0:
        return 0.0
    pi = part.size / costs.size
    margin = float(np.mean(reserve - part))
    return (1.0 - (1.0 - pi) ** j) * margin


def _bin_value(m: Market, i: int, j: int, family: str, single_bin: bool) -> tuple[float, tuple]:
    """Contribution of the bin holding support indices i..j (inclusive).

    Returns (value, cutoffs) where cutoffs[jj-1] is the participation cutoff
    used when jj firms are in the bin and every other firm is in a higher bin.
    """
    sup = m.support
    costs = sup[i : j + 1]
    n, N, r = m.n_values, m.n_firms, m.reserve
    p_s = costs.size / n
    q = (n - 1 - j) / n  # mass strictly above the bin
    weights = [math.comb(N, jj) * p_s**jj * q ** (N - jj) for jj in range(1, N + 1)]
    if family == "plan":
        cut = tuple([r] * N)
        val = sum(w * _tied_value(costs, r, jj, r) for w, jj in zip(weights, range(1, N + 1)))
        return val, cut
    cand = [int(costs[0]) - 1] + [int(c) for c in costs if c <= r]
    if single_bin:
        # Nobody knows how many firms share the bin: one cutoff for all j.
        best = max(
            (sum(w * _tied_value(costs, r, jj, t) for w, jj in zip(weights, range(1, N + 1))), t)
            for t in cand
        )
        return best[0], tuple([best[1]] * N)
    val, cut = 0.0, []
    for w, jj in zip(weights, range(1, N + 1)):
        if jj == 1:
            v, t = _tied_value(costs, r, 1, r), r
        else:
            v, t = max((_tied_value(costs, r, jj, t), t) for t in cand)
        val += w * v
        cut.append(t)
    return val, tuple(cut)


@lru_cache(maxsize=None)
def best_partition(m: Market, n_bins: int, family: str = "plan") -> tuple[float, tuple, tuple]:
    """Best per-contract industry profit with at most ``n_bins`` bins.

    Returns (value, thresholds, cutoffs_per_bin). ``thresholds`` follow
    analysis/frontier.py: a cost c is in bin sum(c > t for t in thresholds).
    """
    if family not in FAMILIES:
        raise ValueError(f"family must be one of {FAMILIES}")
    n = m.n_values
    n_bins = max(1, min(n_bins, n))
    if n_bins == 1:
        v, cut = _bin_value(m, 0, n - 1, family, single_bin=True)
        return v, (), (cut,)
    g = {(i, j): _bin_value(m, i, j, family, single_bin=False) for i in range(n) for j in range(i, n)}
    # f[b][e] = best value covering support[0:e] with exactly b bins
    neg = -math.inf
    f = [[neg] * (n + 1) for _ in range(n_bins + 1)]
    arg = [[None] * (n + 1) for _ in range(n_bins + 1)]
    f[0][0] = 0.0
    for b in range(1, n_bins + 1):
        for e in range(1, n + 1):
            for s in range(b - 1, e):
                if f[b - 1][s] == neg:
                    continue
                v = f[b - 1][s] + g[(s, e - 1)][0]
                if v > f[b][e] + 1e-15:
                    f[b][e], arg[b][e] = v, s
    b_best = max(range(1, n_bins + 1), key=lambda b: (f[b][n], -b))
    # backtrack
    edges, e, b = [], n, b_best
    while b > 0:
        s = arg[b][e]
        edges.append((s, e - 1))
        e, b = s, b - 1
    edges.reverse()
    sup = m.support
    thresholds = tuple(int(sup[j]) for (_, j) in edges[:-1])
    cutoffs = tuple(g[ed][1] for ed in edges)
    return f[b_best][n], thresholds, cutoffs


def bits_to_full(m: Market) -> int:
    """Smallest per-contract k at which 2^k bins separate every cost value."""
    return max(0, math.ceil(math.log2(m.n_values)))


def per_contract_frontier(m: Market, family: str = "plan") -> dict[int, float]:
    """Best per-contract industry profit using k bits on that contract."""
    return {k: best_partition(m, 2**k, family)[0] for k in range(bits_to_full(m) + 1)}


def full_info_value(m: Market) -> float:
    """Per-contract industry profit when the lowest-cost firm with c <= r wins at r."""
    sup = m.support
    n, N, r = m.n_values, m.n_firms, m.reserve
    # P(min cost = c) for N iid draws
    surv = lambda c: ((sup >= c).sum() / n) ** N
    return float(sum((surv(c) - surv(c + 1)) * (r - c) for c in sup if c <= r))


def allocate(per_k: dict[int, float], k_contracts: int, budget: int) -> tuple[float, tuple[int, ...]]:
    """Knapsack: integer bits per contract, sum <= budget, maximise total value."""
    kmax = max(per_k)
    best = (-math.inf, ())
    for split in itertools.combinations_with_replacement(range(kmax + 1), k_contracts):
        if sum(split) <= budget:
            v = sum(per_k[k] for k in split)
            if v > best[0] + 1e-12:
                best = (v, tuple(sorted(split, reverse=True)))
    return best


def allocate_joint(m: Market, k_contracts: int, budget: int, family: str = "plan") -> tuple[float, tuple[int, ...]]:
    """Mixed-radix codes: m_j bins on contract j with prod(m_j) <= 2^budget.

    A b-bit message can index any product of per-contract bin counts, not only
    powers of two. This is a strictly larger family than the plan's integer
    allocation (reported as ``pi_star_joint``)."""
    cap = 2**budget
    values = {b: best_partition(m, b, family)[0] for b in range(1, m.n_values + 1)}
    best = (-math.inf, ())
    for combo in itertools.combinations_with_replacement(range(1, m.n_values + 1), k_contracts):
        if math.prod(combo) <= cap:
            v = sum(values[b] for b in combo)
            if v > best[0] + 1e-12:
                best = (v, tuple(sorted(combo, reverse=True)))
    return best


def frontier(m: Market, k_contracts: int, family: str = "plan", max_bits: int | None = None,
             joint: bool = False) -> dict[int, tuple[float, tuple[int, ...]]]:
    """Industry profit per round (all K contracts) at each per-firm budget.

    Returns {bits: (value, allocation)}; allocation is bits per contract, or
    bins per contract when ``joint``."""
    per_k = per_contract_frontier(m, family)
    top = bits_to_full(m) * k_contracts if max_bits is None else max_bits
    out = {}
    for b in range(top + 1):
        out[b] = allocate_joint(m, k_contracts, b, family) if joint else allocate(per_k, k_contracts, b)
    return out
