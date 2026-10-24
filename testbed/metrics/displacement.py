"""Displacement ratio (plan §3.3) and a run-level cluster bootstrap.

    displacement = (rise in flow through the other media) / (fall in flow through X)

after a countermeasure on X, comparing a treated cell with its matched
baseline (Base-LOO-X, or the pre-intervention rounds). ~1: the balloon effect;
~0: the information was removed. Undefined (NaN) when flow through X did not
fall by more than ``min_fall`` bits.
"""
from __future__ import annotations

import numpy as np

from ..types import MEDIA
from .flow import flows_by_medium
from .panel import build_panel


def displacement_ratio(before: dict[str, float], after: dict[str, float], target: str,
                       min_fall: float = 1e-9) -> float:
    fall = before[target] - after[target]
    rise = sum(after[m] - before[m] for m in before if m != target)
    return rise / fall if fall > min_fall else float("nan")


def _bits(flows, adjusted):
    return {m: (f.adjusted if adjusted else f.bits) for m, f in flows.items()}


def displacement(base_records, treat_records, target: str, *, media=MEDIA, measure: str = "decode",
                 adjusted: bool = False, n_boot: int = 0, seed: int = 0, min_fall: float = 1e-9,
                 **flow_kw) -> dict:
    """Ratio from two cells, with an optional cluster-bootstrap CI over runs
    (runs resampled independently in each cell). Bootstrap replicates use
    ``n_perm=0``; ``adjusted`` uses the point estimate's null means."""
    base, treat = build_panel(base_records), build_panel(treat_records)
    fb = flows_by_medium(base, measure, media, **flow_kw)
    ft = flows_by_medium(treat, measure, media, **flow_kw)
    before, after = _bits(fb, adjusted), _bits(ft, adjusted)
    out = {"ratio": displacement_ratio(before, after, target, min_fall), "before": before, "after": after}
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        kw = {**flow_kw, "n_perm": 0}
        nb, nt = len(base.run_ids), len(treat.run_ids)
        off_b = {m: before[m] - fb[m].bits for m in media} if adjusted else {m: 0.0 for m in media}
        off_t = {m: after[m] - ft[m].bits for m in media} if adjusted else {m: 0.0 for m in media}
        reps = []
        for _ in range(n_boot):
            pb = base.runs(rng.integers(nb, size=nb))
            pt = treat.runs(rng.integers(nt, size=nt))
            bb = {m: f.bits + off_b[m] for m, f in flows_by_medium(pb, measure, media, **kw).items()}
            bt = {m: f.bits + off_t[m] for m, f in flows_by_medium(pt, measure, media, **kw).items()}
            reps.append(displacement_ratio(bb, bt, target, min_fall))
        reps = np.array(reps)
        ok = reps[~np.isnan(reps)]
        out["boot"] = reps
        out["ci95"] = (float(np.quantile(ok, 0.025)), float(np.quantile(ok, 0.975))) if ok.size else (np.nan, np.nan)
    return out


def cluster_bootstrap(records, statistic, n_boot: int = 200, seed: int = 0) -> dict:
    """Resample runs with replacement; ``statistic(panel) -> float``."""
    p = build_panel(records)
    rng = np.random.default_rng(seed)
    n = len(p.run_ids)
    est = statistic(p)
    reps = np.array([statistic(p.runs(rng.integers(n, size=n))) for _ in range(n_boot)])
    lo, hi = float(np.nanquantile(reps, 0.025)), float(np.nanquantile(reps, 0.975))
    # Plug-in MI is biased under resampling (a run drawn twice duplicates rows,
    # which changes cell occupancy; replicates sit below the estimate), so the
    # reported interval is the bootstrap spread centred on the estimate.
    shift = est - float(np.nanmean(reps))
    return {"estimate": est, "boot": reps, "ci95": (lo + shift, hi + shift), "ci95_percentile": (lo, hi)}
