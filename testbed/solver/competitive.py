"""pi_comp: symmetric Bayes-Nash equilibrium of the first-price procurement auction.

One contract; N firms with iid costs uniform on the integer support; sealed
bids, the lowest bid at or below the reserve r wins and is paid its bid; ties
split at random. Firms with cost >= r abstain (they cannot earn a positive
margin; with cost == r they are indifferent and abstaining is the convention).

Two solvers, cross-checked in tests/test_solver_competitive.py:

``analytic_equilibrium``
    With discrete types the symmetric equilibrium is in mixed strategies on
    contiguous, ordered bid intervals (Maskin & Riley 1985 style). The highest
    participating type c_m mixes on [L_m, r]; type c_j mixes on [L_j, L_{j+1}].
    Indifference on each interval gives, with q_j = P(cost > c_j),

        pi_j = (U_j - c_j) * q_j^(N-1),     L_j = c_j + pi_j / q_{j-1}^(N-1),

    starting from U_m = r. This is exact (continuous bids, no atoms).

``fictitious_play``
    Numerical check on a bid grid: every type best-responds to the running
    average of the population strategy; the average is the equilibrium
    estimate. Accuracy is reported as exploitability, the largest gain any
    type could get by deviating to another grid bid against the average
    strategy. Discretisation shifts profits by O(grid step).

``pi_comp`` in ``benchmarks()`` is the analytic value; ``exploitability`` of
that equilibrium (checked against a fine bid grid) is reported with it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .collusive import Market


@dataclass
class AnalyticEq:
    types: np.ndarray       # participating cost values, ascending
    lower: np.ndarray       # L_j
    upper: np.ndarray       # U_j
    profit: np.ndarray      # pi_j, expected profit of type j per contract
    q: np.ndarray           # P(cost > c_j)
    p: float                # P(cost == c) for one value
    n_firms: int

    def cdf(self, j: int, b: np.ndarray) -> np.ndarray:
        """F_j(b): type j's bid CDF on its interval."""
        b = np.asarray(b, dtype=float)
        e = 1.0 / (self.n_firms - 1)
        with np.errstate(divide="ignore", invalid="ignore"):
            inner = (self.profit[j] / np.maximum(b - self.types[j], 1e-300)) ** e
        f = 1.0 - (inner - self.q[j]) / self.p
        f = np.where(b < self.lower[j], 0.0, np.where(b >= self.upper[j], 1.0, f))
        return np.clip(f, 0.0, 1.0)

    def win_prob(self, b: np.ndarray) -> np.ndarray:
        """Probability that bid b beats all N-1 rivals playing the equilibrium."""
        b = np.asarray(b, dtype=float)
        # P(one rival bids above b), counting non-participants as "above"
        above = np.full(b.shape, 1.0 - self.p * len(self.types))
        for j in range(len(self.types)):
            above = above + self.p * (1.0 - self.cdf(j, b))
        return above ** (self.n_firms - 1)

    def expected_profit_per_firm(self) -> float:
        return float(self.p * self.profit.sum())


def analytic_equilibrium(m: Market) -> AnalyticEq:
    if m.n_firms < 2:
        raise ValueError("need at least 2 firms")
    sup = m.support.astype(float)
    n, N, r = m.n_values, m.n_firms, float(m.reserve)
    p = 1.0 / n
    types = sup[sup < r]
    q = np.array([(sup > c).sum() / n for c in types])
    lower, upper, profit = np.zeros(len(types)), np.zeros(len(types)), np.zeros(len(types))
    u = r
    for j in range(len(types) - 1, -1, -1):
        upper[j] = u
        profit[j] = (u - types[j]) * q[j] ** (N - 1)
        q_prev = q[j] + p  # P(cost > c_{j-1}) = P(cost >= c_j)
        lower[j] = types[j] + profit[j] / q_prev ** (N - 1)
        u = lower[j]
    return AnalyticEq(types, lower, upper, profit, q, p, N)


def exploitability(eq: AnalyticEq, reserve: float, grid_step: float = 0.001) -> float:
    """Largest gain any type gets from a deviation bid on a fine grid."""
    grid = np.arange(eq.types[0], reserve + grid_step / 2, grid_step)
    w = eq.win_prob(grid)
    gain = 0.0
    for j, c in enumerate(eq.types):
        dev = np.max((grid - c) * w)
        gain = max(gain, dev - eq.profit[j])
    return float(gain)


@dataclass
class FPResult:
    grid: np.ndarray
    strategy: np.ndarray     # [n_types, n_grid + 1]; last column = abstain
    types: np.ndarray
    profit_per_firm: float   # expected profit per firm per contract
    exploitability: float
    iterations: int


def _win_prob_grid(opp: np.ndarray, n_firms: int) -> np.ndarray:
    """opp: distribution of one rival's bid over [grid..., abstain].

    Returns the probability of winning at each grid bid, ties split."""
    g = opp[:-1]
    above = np.concatenate([np.cumsum(g[::-1])[::-1][1:], [0.0]]) + opp[-1]
    k = n_firms - 1
    w = np.zeros_like(g)
    for t in range(k + 1):
        w += math.comb(k, t) * g**t * above ** (k - t) / (t + 1)
    return w


def fictitious_play(m: Market, grid_step: float = 0.05, iterations: int = 20000,
                    tol: float | None = None) -> FPResult:
    """Fictitious play on a bid grid {cost_low .. r} in steps of ``grid_step``.

    Stops early once exploitability < ``tol`` (checked every 500 iterations)."""
    sup = m.support.astype(float)
    n, N, r = m.n_values, m.n_firms, float(m.reserve)
    types = sup[sup < r]
    grid = np.round(np.arange(m.cost_low, r + grid_step / 2, grid_step), 10)
    n_t, n_g = len(types), len(grid)
    pay = grid[None, :] - types[:, None]               # margin at each bid
    avg = np.zeros((n_t, n_g + 1))
    avg[np.arange(n_t), np.argmin(np.abs(grid[None, :] - r), axis=1)] = 1.0  # start at r
    w_type = np.full(n_t, 1.0 / n)
    p_abstain = (n - n_t) / n

    def opp_dist(s):
        d = (w_type[:, None] * s).sum(axis=0)
        d[-1] += p_abstain
        return d

    def regret(s):
        w = _win_prob_grid(opp_dist(s), N)
        u = pay * w[None, :]
        u_full = np.concatenate([u, np.zeros((n_t, 1))], axis=1)
        cur = (u_full * s).sum(axis=1)
        return float(np.max(u_full.max(axis=1) - cur)), u_full

    it = 0
    for it in range(1, iterations + 1):
        _, u_full = regret(avg)
        br = np.zeros_like(avg)
        br[np.arange(n_t), np.argmax(u_full, axis=1)] = 1.0
        avg += (br - avg) / (it + 1)
        if tol is not None and it % 500 == 0 and regret(avg)[0] < tol:
            break
    eps, u_full = regret(avg)
    profit = float((w_type * (u_full * avg).sum(axis=1)).sum())
    return FPResult(grid, avg, types, profit, eps, it)
