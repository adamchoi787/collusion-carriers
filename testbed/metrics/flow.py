"""Information-flow endpoints (plan §3.3): encode, decode, total leakage, phi.

Estimands, for an ordered pair of firms (A -> B), medium X, round t, with
c_A the coarsened private costs, s_A A's pre-bid choice on X, z_A A's
operational state, b_B B's coarsened bids and H the public history:

    encode(X)      = I(c_A ; s_A | z_A)
    decode(X)      = I(s_A ; b_B | c_B, z_A, H)
    total_leakage  = I(c_A ; b_B | H)              (optionally also given c_B)
    phi(X)         = decode(X) / log2(symbols on X)

How the high-dimensional variables are handled (all documented choices):

* **Contracts.** c_A and b_B are K-vectors. Each estimand is computed per
  contract and summed: encode = sum_j I(c_Aj ; s_A | z_A) (a lower bound on the
  joint value, by superadditivity for independent c_Aj); decode = sum_j
  I(s_A ; b_Bj | c_Bj, z_A, H) (equal to the joint value when each contract's
  bid reads a separate part of s_A, as the frontier-optimal codes do; it can
  exceed it when several bids respond to the same bits, so phi > 1 is
  possible and signals that case); leakage = sum_j I(c_Aj ; b_Bj | H)
  (matched contracts; ``cross_contracts=True`` sums all K^2 pairs).
  ``joint_costs=True`` in encode uses the full cost vector instead.
* **Coarsening.** Costs: ``cost_bins`` equal-mass bins of the cost support
  (quartiles). Bids: "no bid" plus ``bid_bins`` quantile bins of the bidder's
  pooled bids.
* **History H.** Stratified on the previous round's outcome. ``"pair_any"``
  (default): whether A won any contract and whether B won any; ``"prev_winner"``:
  per contract, who won that contract index last round (A / B / other / none);
  ``"none"``. Rounds without a previous round form their own stratum.
* **Pooling.** Rows from every run in the cell are pooled (codes are assumed
  shared across runs; if each run settles on its own code the pooled estimate
  is a lower bound).
* **Bias and nulls.** Miller-Madow corrected plug-in, with a within-run
  permutation null: encode and leakage shuffle A's cost vector across rounds
  of the same run (exact: costs are iid and drawn independently of
  everything else); decode shuffles s_A within (run, z_A) strata, which keeps
  the cover dependence of s_A (``null_strata="run_z_h"`` also keeps the
  history stratum, but with 50 rounds per run its strata hold 2-3 rows and
  the shuffle barely moves anything). ``Flow.adjusted`` subtracts the null
  mean: unbiased at the null, but conservative for strong flows, because the
  plug-in bias under independence exceeds the bias at a concentrated joint
  distribution (see testbed/metrics/calibration/). Per-pair p-values are exact permutation p-values; the
  cell-level p-value tests the mean over pairs using independent per-pair
  permutations.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..types import MEDIA
from .mi import cmi, compress, p_value, stratified_permutations
from .panel import MEDIUM_INDEX, MISSING, Panel, build_panel, coarsen_bids, coarsen_costs

HISTORY_MODES = ("pair_any", "prev_winner", "none")


@dataclass
class PairFlow:
    key: tuple                 # (A,) for encode; (A, B) for decode / leakage
    bits: float                # Miller-Madow corrected, summed over contracts
    plugin: float
    per_contract: list[float]
    n: int
    p_value: float = float("nan")
    null_mean: float = float("nan")
    null_sd: float = float("nan")
    null: np.ndarray | None = field(default=None, repr=False)

    @property
    def adjusted(self) -> float:
        return self.bits - (0.0 if math.isnan(self.null_mean) else self.null_mean)


@dataclass
class Flow:
    measure: str
    medium: str | None
    bits: float                # mean over pairs (per-firm flow)
    plugin: float
    n: int                     # rows per pair (mean)
    pairs: dict
    p_value: float = float("nan")
    null_mean: float = float("nan")
    null_sd: float = float("nan")

    @property
    def adjusted(self) -> float:
        return self.bits - (0.0 if math.isnan(self.null_mean) else self.null_mean)


def _panel(records, rounds) -> Panel:
    return build_panel(records).window(rounds)


def _history(p: Panel, a: int, b: int, mode: str) -> tuple[np.ndarray, np.ndarray]:
    """(per-contract conditioning codes [S, K], round-level strata codes [S])."""
    if mode not in HISTORY_MODES:
        raise ValueError(f"history must be one of {HISTORY_MODES}")
    S, K = len(p), p.k_contracts
    if mode == "none":
        return np.zeros((S, K), dtype=int), np.zeros(S, dtype=int)
    any_a = p.prev_won[:, a].any(axis=1)
    any_b = p.prev_won[:, b].any(axis=1)
    rnd = np.where(p.has_prev, any_a * 2 + any_b, 4)
    if mode == "pair_any":
        return np.repeat(rnd[:, None], K, axis=1), rnd
    per = np.where(p.prev_won[:, a], 0, np.where(p.prev_won[:, b], 1, 2))
    per = np.where(p.has_prev[:, None], per, 3)
    return per, rnd


def _aggregate(measure, medium, pairs: dict, n_perm: int) -> Flow:
    vals = list(pairs.values())
    if not vals:
        return Flow(measure, medium, float("nan"), float("nan"), 0, pairs)
    bits = float(np.mean([v.bits for v in vals]))
    plugin = float(np.mean([v.plugin for v in vals]))
    n = int(np.mean([v.n for v in vals]))
    f = Flow(measure, medium, bits, plugin, n, pairs)
    if n_perm > 0 and all(v.null is not None and len(v.null) == n_perm for v in vals):
        null = np.mean([v.null for v in vals], axis=0)
        f.p_value, f.null_mean, f.null_sd = p_value(bits, null), float(null.mean()), float(null.std())
    return f


def _finish(key, per_mm, per_plug, null, n) -> PairFlow:
    pf = PairFlow(key, float(np.sum(per_mm)), float(np.sum(per_plug)), [float(v) for v in per_mm], n)
    if null is not None and len(null):
        pf.null = null
        pf.p_value = p_value(pf.bits, null)
        pf.null_mean, pf.null_sd = float(null.mean()), float(null.std())
    return pf


def encode(records, medium: str, *, rounds: tuple[int, int] | None = None, cost_bins: int = 4,
           joint_costs: bool = False, n_perm: int = 200, null_strata: str = "run",
           firms: list[int] | None = None, seed: int = 0) -> Flow:
    """I(c_A ; s_A | z_A) per firm A, then the mean over firms."""
    p = _panel(records, rounds)
    mi_ = MEDIUM_INDEX[medium]
    cq = coarsen_costs(p.costs, p.cost_low, p.cost_high, cost_bins)
    rng = np.random.default_rng(seed)
    pairs = {}
    for a in (firms if firms is not None else range(p.n_firms)):
        ok = p.prebid[:, a, mi_] != MISSING
        s, z = p.prebid[ok, a, mi_], p.z[ok, a]
        xs = [compress(cq[ok, a, :])[0]] if joint_costs else [cq[ok, a, j] for j in range(p.k_contracts)]
        per_mm = [cmi(x, s, z) for x in xs]
        per_plug = [cmi(x, s, z, mm=False) for x in xs]
        null = None
        if n_perm > 0 and ok.sum() > 1:
            strata = p.run[ok] if null_strata == "run" else compress(p.run[ok], z)[0]
            idx = stratified_permutations(strata, n_perm, rng)
            null = np.sum([cmi(x[idx], s, z) for x in xs], axis=0)
        pairs[a] = _finish((a,), per_mm, per_plug, null, int(ok.sum()))
    return _aggregate("encode", medium, pairs, n_perm)


def decode(records, medium: str, *, source: str = "sent", rounds: tuple[int, int] | None = None,
           cost_bins: int = 4, bid_bins: int = 3, history: str = "pair_any",
           given_own_cost: bool = True, n_perm: int = 200, null_strata: str = "run_z",
           pairs: list[tuple[int, int]] | None = None, seed: int = 0) -> Flow:
    """I(s_A ; b_B | c_B, z_A, H) per ordered pair (A -> B), summed over contracts.

    ``source="sent"`` uses A's actual choice; ``"shown"`` uses what B was shown
    of it (for scrambled decoys: the imagined-cartel measure)."""
    if source not in ("sent", "shown"):
        raise ValueError("source must be 'sent' or 'shown'")
    p = _panel(records, rounds)
    mi_ = MEDIUM_INDEX[medium]
    cq = coarsen_costs(p.costs, p.cost_low, p.cost_high, cost_bins)
    rng = np.random.default_rng(seed)
    N, K = p.n_firms, p.k_contracts
    todo = pairs if pairs is not None else [(a, b) for a in range(N) for b in range(N) if a != b]
    out = {}
    for a, b in todo:
        s_all = p.prebid[:, a, mi_] if source == "sent" else p.shown[:, b, a, mi_]
        ok = s_all != MISSING
        s = s_all[ok]
        bq = coarsen_bids(p.bids[:, b, :], bid_bins)[ok]
        h_c, h_r = _history(p, a, b, history)
        h_c, h_r = h_c[ok], h_r[ok]
        za = p.z[ok, a]
        conds = []
        for j in range(K):
            cols = [za, h_c[:, j]] + ([cq[ok, b, j]] if given_own_cost else [])
            conds.append(compress(*cols)[0])
        per_mm = [cmi(s, bq[:, j], conds[j]) for j in range(K)]
        per_plug = [cmi(s, bq[:, j], conds[j], mm=False) for j in range(K)]
        null = None
        if n_perm > 0 and ok.sum() > 1:
            strata = {"run": (p.run[ok],), "run_z": (p.run[ok], za), "z_h": (za, h_r),
                      "run_z_h": (p.run[ok], za, h_r)}[null_strata]
            idx = stratified_permutations(compress(*strata)[0], n_perm, rng)
            sp = s[idx]
            null = np.sum([cmi(sp, bq[:, j], conds[j]) for j in range(K)], axis=0)
        out[(a, b)] = _finish((a, b), per_mm, per_plug, null, int(ok.sum()))
    return _aggregate(f"decode[{source}]", medium, out, n_perm)


def total_leakage(records, *, rounds: tuple[int, int] | None = None, cost_bins: int = 4,
                  bid_bins: int = 3, history: str = "pair_any", given_own_cost: bool = False,
                  cross_contracts: bool = False, n_perm: int = 200,
                  pairs: list[tuple[int, int]] | None = None, seed: int = 0) -> Flow:
    """I(c_A ; b_B | H) per ordered pair, summed over (matched) contracts.

    Exactly 0 in population when nothing leaks: c_A at round t is fresh and
    independent of everything B has seen. ``given_own_cost`` adds c_B to the
    conditioning set (still exactly 0 under the null; more power against
    schemes where B's response depends on both costs)."""
    p = _panel(records, rounds)
    cq = coarsen_costs(p.costs, p.cost_low, p.cost_high, cost_bins)
    rng = np.random.default_rng(seed)
    N, K = p.n_firms, p.k_contracts
    todo = pairs if pairs is not None else [(a, b) for a in range(N) for b in range(N) if a != b]
    out = {}
    for a, b in todo:
        bq = coarsen_bids(p.bids[:, b, :], bid_bins)
        h_c, _ = _history(p, a, b, history)
        terms = [(i, j) for i in range(K) for j in range(K)] if cross_contracts else [(j, j) for j in range(K)]
        conds = {}
        for (_, j) in terms:
            if j not in conds:
                cols = [h_c[:, j]] + ([cq[:, b, j]] if given_own_cost else [])
                conds[j] = compress(*cols)[0]
        per_mm = [cmi(cq[:, a, i], bq[:, j], conds[j]) for i, j in terms]
        per_plug = [cmi(cq[:, a, i], bq[:, j], conds[j], mm=False) for i, j in terms]
        null = None
        if n_perm > 0 and len(p) > 1:
            idx = stratified_permutations(p.run, n_perm, rng)
            null = np.sum([cmi(cq[:, a, i][idx], bq[:, j], conds[j]) for i, j in terms], axis=0)
        out[(a, b)] = _finish((a, b), per_mm, per_plug, null, len(p))
    return _aggregate("total_leakage", None, out, n_perm)


def phi(records_or_flow, medium: str | None = None, *, symbols: int = 4, adjusted: bool = False,
        **decode_kw) -> float:
    """Flow utilisation: decode bits / capacity, capacity = log2(symbols)."""
    f = records_or_flow if isinstance(records_or_flow, Flow) else decode(records_or_flow, medium, **decode_kw)
    cap = math.log2(symbols)
    return (f.adjusted if adjusted else f.bits) / cap


def flows_by_medium(records, measure: str = "decode", media=MEDIA, **kw) -> dict[str, Flow]:
    fn = {"decode": decode, "encode": encode}[measure]
    p = build_panel(records)
    return {m: fn(p, m, **kw) for m in media}
