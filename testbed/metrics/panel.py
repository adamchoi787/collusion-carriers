"""Array view of round records: one row per (run, round), firms and contracts as axes."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

import numpy as np

from ..types import MEDIA
from .io import headers, round_records

MEDIUM_INDEX = {m: i for i, m in enumerate(MEDIA)}
MISSING = -1


@dataclass
class Panel:
    run: np.ndarray        # [S] index into run_ids
    round: np.ndarray      # [S]
    costs: np.ndarray      # [S, N, K] int
    z: np.ndarray          # [S, N]
    defaults: np.ndarray   # [S, N, M]   MISSING if absent
    prebid: np.ndarray     # [S, N, M]   MISSING if absent
    shown: np.ndarray      # [S, N(viewer), N(source), M]  MISSING = unavailable
    bids: np.ndarray       # [S, N, K] float, nan = no bid
    won: np.ndarray        # [S, N, K] bool
    profit: np.ndarray     # [S, N]
    fine: np.ndarray       # [S, N]
    prev_won: np.ndarray   # [S, N, K] bool, previous round of the same run
    has_prev: np.ndarray   # [S] bool
    run_ids: list
    cost_low: int = 1
    cost_high: int = 12
    reserve: float = 10.0

    @property
    def n_firms(self) -> int:
        return self.costs.shape[1]

    @property
    def k_contracts(self) -> int:
        return self.costs.shape[2]

    def __len__(self) -> int:
        return len(self.round)

    def select(self, mask: np.ndarray) -> "Panel":
        kw = {}
        for f in fields(self):
            v = getattr(self, f.name)
            kw[f.name] = v[mask] if isinstance(v, np.ndarray) else v
        return replace(self, **kw)

    def window(self, rounds: tuple[int, int] | None) -> "Panel":
        if rounds is None:
            return self
        lo, hi = rounds
        return self.select((self.round >= lo) & (self.round <= hi))

    def runs(self, idx) -> "Panel":
        """Rows of the given run indices (with repetition, for the cluster bootstrap)."""
        parts = [np.flatnonzero(self.run == i) for i in idx]
        rows = np.concatenate(parts) if parts else np.zeros(0, int)
        p = self.select(rows)
        # relabel so resampled copies of one run count as distinct runs
        p.run = np.concatenate([np.full(len(x), j) for j, x in enumerate(parts)]) if parts else rows
        p.run_ids = [self.run_ids[i] for i in idx]
        return p


def _won_flags(w, k):
    if w is None:
        return [False] * k
    if len(w) == k and all(isinstance(x, (bool, int)) and x in (0, 1, True, False) for x in w):
        return [bool(x) for x in w]
    flags = [False] * k
    for j in w:
        flags[int(j)] = True
    return flags


def _sym(v):
    return MISSING if v is None or isinstance(v, str) else int(v)


def build_panel(records, cost_low: int | None = None, cost_high: int | None = None,
                reserve: float | None = None) -> Panel:
    """Assemble a Panel. Rounds where any firm's record is missing are dropped."""
    if isinstance(records, Panel):
        return records
    recs = round_records(records)
    if not recs:
        raise ValueError("no round records")
    hdr = headers(records)
    cfg = next(iter(hdr.values()), {}).get("config", {}) if hdr else {}
    n = 1 + max(int(r["firm"]) for r in recs)
    k = len(recs[0]["costs"])
    m = len(MEDIA)

    run_ids = sorted({r.get("run", "0") for r in recs})
    run_index = {rid: i for i, rid in enumerate(run_ids)}
    by_key: dict[tuple[int, int], dict[int, dict]] = {}
    for r in recs:
        by_key.setdefault((run_index[r.get("run", "0")], int(r["round"])), {})[int(r["firm"])] = r
    keys = sorted(kk for kk, v in by_key.items() if len(v) == n)
    S = len(keys)

    run = np.array([kk[0] for kk in keys], dtype=int)
    rnd = np.array([kk[1] for kk in keys], dtype=int)
    costs = np.zeros((S, n, k), dtype=int)
    z = np.zeros((S, n), dtype=int)
    defaults = np.full((S, n, m), MISSING, dtype=int)
    prebid = np.full((S, n, m), MISSING, dtype=int)
    shown = np.full((S, n, n, m), MISSING, dtype=int)
    bids = np.full((S, n, k), np.nan)
    won = np.zeros((S, n, k), dtype=bool)
    profit = np.zeros((S, n))
    fine = np.zeros((S, n))
    for s, kk in enumerate(keys):
        for i, r in by_key[kk].items():
            costs[s, i] = r["costs"]
            z[s, i] = int(r.get("z", 0))
            for med, v in (r.get("defaults") or {}).items():
                if med in MEDIUM_INDEX:
                    defaults[s, i, MEDIUM_INDEX[med]] = _sym(v)
            for med, v in (r.get("prebid") or {}).items():
                if med in MEDIUM_INDEX:
                    prebid[s, i, MEDIUM_INDEX[med]] = _sym(v)
            for src, vals in (r.get("shown") or {}).items():
                for med, v in (vals or {}).items():
                    if med in MEDIUM_INDEX:
                        shown[s, i, int(src), MEDIUM_INDEX[med]] = _sym(v)
            b = r.get("bids") or [None] * k
            bids[s, i] = [np.nan if x is None else float(x) for x in b]
            won[s, i] = _won_flags(r.get("won"), k)
            profit[s, i] = float(r.get("profit") or 0.0)
            fine[s, i] = float(r.get("fine") or 0.0)

    prev_won = np.zeros_like(won)
    has_prev = np.zeros(S, dtype=bool)
    pos = {kk: s for s, kk in enumerate(keys)}
    for s, (ri, t) in enumerate(keys):
        p = pos.get((ri, t - 1))
        if p is not None:
            prev_won[s] = won[p]
            has_prev[s] = True

    lo = cost_low if cost_low is not None else cfg.get("cost_low", int(costs.min()))
    hi = cost_high if cost_high is not None else cfg.get("cost_high", int(costs.max()))
    res = reserve if reserve is not None else cfg.get("reserve", 10.0)
    return Panel(run, rnd, costs, z, defaults, prebid, shown, bids, won, profit, fine,
                 prev_won, has_prev, run_ids, int(lo), int(hi), float(res))


def coarsen_costs(costs: np.ndarray, cost_low: int, cost_high: int, bins: int = 4) -> np.ndarray:
    """Equal-mass bins of the uniform cost support (quartiles by default)."""
    n_values = cost_high - cost_low + 1
    q = ((costs - cost_low) * bins) // n_values
    return np.clip(q, 0, bins - 1).astype(int)


def coarsen_bids(bids: np.ndarray, bins: int = 3) -> np.ndarray:
    """Category 0 = no bid; 1..bins = quantile bins of the numeric bids pooled
    over the array (duplicate edges merged)."""
    out = np.zeros(bids.shape, dtype=int)
    ok = ~np.isnan(bids)
    if ok.any():
        edges = np.unique(np.quantile(bids[ok], np.linspace(0, 1, bins + 1)[1:-1]))
        out[ok] = 1 + np.searchsorted(edges, bids[ok], side="right")
    return out
