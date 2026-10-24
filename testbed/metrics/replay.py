"""Counterfactual replay (plan §3.3, per-medium attribution).

At B's bid decision in round t, replace what B was shown of rival A's medium X
with what B was shown of it in a donor round t' of the same run where A's
(coarsened) costs differed, re-query B, and compare B's bids with bids from
re-queries on the unchanged content. Sampling noise in B is measured by a
"same content, resampled" null: two independent batches on the original
content. Causal flow through X at this decision point is

    flow = distance(original batch 1, counterfactual batch) - distance(original batch 1, original batch 2)

``agent_factory(run, round, firm)`` must return a fresh Agent in the state it
had just before that round's bid phase (the engine provides this from its
checkpoints: ``restore(snapshot)``). It is called once per query, so queries
never see each other. ``observation_builder`` defaults to rebuilding the bid
phase Observation from the log (costs, z, defaults, the shown pre-bid values,
a compact public history, fines); pass the engine's builder to get the exact
prompt state, including framing and messages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from ..types import Observation
from .io import round_records
from .panel import coarsen_costs


def _index(records) -> dict:
    return {(r.get("run", "0"), int(r["round"]), int(r["firm"])): r for r in round_records(records)}


def observation_from_log(records, run, round: int, firm: int, *,
                         override: dict[int, dict[str, int | str]] | None = None,
                         phase: str = "bid", _idx: dict | None = None) -> Observation:
    idx = _idx if _idx is not None else _index(records)
    rec = idx[(run, round, firm)]
    rivals = {int(a): dict(v) for a, v in (rec.get("shown") or {}).items()}
    for a, vals in (override or {}).items():
        rivals.setdefault(int(a), {}).update(vals)
    history, fines = [], 0.0
    past = sorted(t for (r_, t, f) in idx if r_ == run and f == firm and t < round)
    for t in past:
        row = {"round": t, "bids": {}, "won": {}, "activity": {}}
        for (r_, t_, f), rr in idx.items():
            if r_ == run and t_ == t:
                row["bids"][f] = rr.get("bids")
                row["won"][f] = rr.get("won")
        row["activity"] = idx[(run, t, firm)].get("shown", {})
        history.append(row)
        fines += float(idx[(run, t, firm)].get("fine") or 0.0)
    return Observation(firm=firm, round=round, phase=phase, costs=list(rec["costs"]), z=int(rec.get("z", 0)),
                       defaults=dict(rec.get("defaults") or {}), framing={}, rivals_prebid=rivals,
                       history=history, fines=fines)


def _as_matrix(bids: list, k: int, abstain_value: float) -> np.ndarray:
    m = np.full((len(bids), k), abstain_value, dtype=float)
    for i, row in enumerate(bids):
        for j, b in enumerate((row or [])[:k]):
            if b is not None:
                m[i, j] = float(b)
    return m


def mean_abs_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean over contracts of |mean bid in a - mean bid in b|."""
    return float(np.mean(np.abs(a.mean(axis=0) - b.mean(axis=0))))


def tv_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean over contracts of the total-variation distance between bid distributions."""
    out = []
    for j in range(a.shape[1]):
        vals = np.union1d(a[:, j], b[:, j])
        pa = np.array([(a[:, j] == v).mean() for v in vals])
        pb = np.array([(b[:, j] == v).mean() for v in vals])
        out.append(0.5 * np.abs(pa - pb).sum())
    return float(np.mean(out))


@dataclass
class ReplayResult:
    run: str
    round: int
    firm: int
    rival: int
    medium: str
    donor_round: int
    original: int | str
    counterfactual: int | str
    original_bids: np.ndarray = field(repr=False)        # [2 * n_samples, K]
    counterfactual_bids: np.ndarray = field(repr=False)  # [n_samples, K]
    effect: float = 0.0
    null_effect: float = 0.0

    @property
    def flow(self) -> float:
        return self.effect - self.null_effect

    @property
    def content_changed(self) -> bool:
        return self.original != self.counterfactual


def replay(records, round: int, firm: int, medium: str, agent_factory: Callable, n_samples: int = 5, *,
           run=None, rival: int | None = None, donor_round: int | None = None,
           observation_builder: Callable | None = None, cost_bins: int = 4,
           distance: Callable = mean_abs_distance, abstain_value: float | None = None,
           seed: int = 0) -> ReplayResult:
    """One counterfactual replay at (run, round, firm) for the rival's medium."""
    idx = _index(records)
    runs = sorted({k[0] for k in idx})
    if run is None:
        if len(runs) != 1:
            raise ValueError("records hold several runs; pass run=")
        run = runs[0]
    firms = sorted({k[2] for k in idx if k[0] == run})
    if rival is None:
        others = [f for f in firms if f != firm]
        if len(others) != 1:
            raise ValueError("several rivals; pass rival=")
        rival = others[0]
    hdr = next((r for r in records if r.get("type") == "header" and r.get("run") == run), {})
    cfg = hdr.get("config", {})
    lo, hi, reserve = cfg.get("cost_low", 1), cfg.get("cost_high", 12), float(cfg.get("reserve", 10))
    abstain = reserve + 1 if abstain_value is None else abstain_value

    me = idx[(run, round, firm)]
    original = (me.get("shown") or {}).get(str(rival), (me.get("shown") or {}).get(rival, {})).get(medium, "unavailable")
    if original == "unavailable":
        raise ValueError(f"{medium} of firm {rival} was not shown to firm {firm} in round {round}")

    def shown_at(t):
        sh = idx[(run, t, firm)].get("shown") or {}
        return sh.get(str(rival), sh.get(rival, {})).get(medium, "unavailable")

    if donor_round is None:
        cq = lambda t: tuple(coarsen_costs(np.array(idx[(run, t, rival)]["costs"]), lo, hi, cost_bins))
        here = cq(round)
        cands = [t for (r_, t, f) in idx if r_ == run and f == firm and t != round
                 and (run, t, rival) in idx and cq(t) != here and shown_at(t) != "unavailable"]
        if not cands:
            raise ValueError("no donor round with different rival costs")
        donor_round = int(np.random.default_rng(seed).choice(sorted(cands)))
    cf = shown_at(donor_round)

    build = observation_builder or (lambda recs, run_, t, f, override: observation_from_log(
        recs, run_, t, f, override=override, _idx=idx))
    k = len(me["costs"])

    def query(content, n):
        out = []
        for _ in range(n):
            agent = agent_factory(run, round, firm)
            obs = build(records, run, round, firm, {rival: {medium: content}})
            out.append(list(agent.act(obs).bids or [None] * k))
        return _as_matrix(out, k, abstain)

    orig = query(original, 2 * n_samples)
    cfb = query(cf, n_samples)
    a, b = orig[:n_samples], orig[n_samples:]
    return ReplayResult(run, round, firm, rival, medium, donor_round, original, cf, orig, cfb,
                        distance(a, cfb), distance(a, b))


def replay_many(records, medium: str, agent_factory: Callable, points: list[tuple], n_samples: int = 5,
                **kw) -> dict:
    """Replay at several (run, round, firm) points; mean flow and per-point results."""
    res = [replay(records, t, f, medium, agent_factory, n_samples, run=r, **kw) for (r, t, f) in points]
    flows = np.array([x.flow for x in res])
    return {"flow": float(flows.mean()) if len(flows) else float("nan"),
            "share_positive": float((flows > 0).mean()) if len(flows) else float("nan"), "results": res}
