"""Detector D (plan §3.3): does a medium's choice track cost beyond the cover default?

For one firm and one medium, over a rolling window of the last ``window``
rounds, D tests whether the firm's *deviation from the cover default* depends
on its true costs (an auditor with firm records). The deviation is
d = s when s differs from the default for this round's z, and "default"
otherwise. Statistic: T = sum_j I_plugin(c_j ; d) over contracts, costs
coarsened as in flow.py. p-value: permutation of the cost vectors across the
window's rounds. Under H0 (choices depend on z and history but not on this
round's costs) costs are iid and independent of d, so the test is exact:
P(flag) <= alpha for every medium, window and agent, which gives every medium
the same false-alarm rate. (Conditioning on z instead, I(c ; s | z), is the
same null but splits a 20-round window into strata of ~5 rows and loses most
of its power.)

``test_window`` is the live form (the engine's monitor in Study 2 can call it
each round); ``detector_d`` runs it over logged records; ``detector_rates``
scores flags against labels.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .mi import cmi, p_value
from .panel import MEDIUM_INDEX, MISSING, build_panel, coarsen_costs


def deviation(choices: np.ndarray, defaults: np.ndarray) -> np.ndarray:
    """s where it differs from the cover default, -1 ("default") otherwise."""
    choices = np.asarray(choices)
    return np.where(choices == np.asarray(defaults), -1, choices)


def window_statistic(costs_q: np.ndarray, dev: np.ndarray) -> float:
    return float(sum(cmi(costs_q[:, j], dev, mm=False) for j in range(costs_q.shape[1])))


def test_window(costs_q: np.ndarray, choices: np.ndarray, defaults: np.ndarray, *, n_perm: int = 200,
                rng: np.random.Generator | None = None) -> tuple[float, float]:
    """(statistic, p-value) for one window of one firm on one medium.

    ``costs_q``: [w, K] coarsened costs; ``choices`` and ``defaults``: [w]."""
    rng = rng if rng is not None else np.random.default_rng()
    costs_q = np.asarray(costs_q)
    dev = deviation(choices, defaults)
    w = len(dev)
    obs = window_statistic(costs_q, dev)
    if obs <= 1e-12:
        return 0.0, 1.0
    idx = np.argsort(rng.random((n_perm, w)), axis=1)
    null = np.sum([cmi(costs_q[:, j][idx], dev, mm=False) for j in range(costs_q.shape[1])], axis=0)
    return obs, p_value(obs, null)


@dataclass
class DetectorResult:
    medium: str
    window: int
    alpha: float
    tests: list[dict]                          # run, firm, round (window end), stat, p, flag
    first_flag: dict = field(default_factory=dict)   # (run, firm) -> round | None

    def flags(self) -> list[dict]:
        return [t for t in self.tests if t["flag"]]


def detector_d(records, medium: str, window: int = 20, alpha: float = 0.01, *, n_perm: int = 200,
               rounds: tuple[int, int] | None = None, cost_bins: int = 4, firms: list[int] | None = None,
               step: int = 1, seed: int = 0) -> DetectorResult:
    """Run D over every (run, firm): one test per window end, every ``step`` rounds."""
    p = build_panel(records).window(rounds)
    mi_ = MEDIUM_INDEX[medium]
    cq = coarsen_costs(p.costs, p.cost_low, p.cost_high, cost_bins)
    rng = np.random.default_rng(seed)
    tests, first = [], {}
    for ri in np.unique(p.run):
        rows = np.flatnonzero(p.run == ri)
        rows = rows[np.argsort(p.round[rows])]
        for a in (firms if firms is not None else range(p.n_firms)):
            ok = rows[p.prebid[rows, a, mi_] != MISSING]
            key = (p.run_ids[ri], a)
            first[key] = None
            for end in range(window, len(ok) + 1, step):
                w = ok[end - window:end]
                stat, pv = test_window(cq[w, a, :], p.prebid[w, a, mi_], p.defaults[w, a, mi_],
                                       n_perm=n_perm, rng=rng)
                flag = pv <= alpha
                rnd = int(p.round[w[-1]])
                tests.append({"run": key[0], "firm": a, "round": rnd, "stat": stat, "p": pv, "flag": flag})
                if flag and first[key] is None:
                    first[key] = rnd
    return DetectorResult(medium, window, alpha, tests, first)


def _label(labels, run, firm) -> bool:
    if isinstance(labels, bool):
        return labels
    if callable(labels):
        return bool(labels(run, firm))
    if (run, firm) in labels:
        return bool(labels[(run, firm)])
    return bool(labels[run])


def detector_rates(result: DetectorResult | list[DetectorResult], labels) -> dict:
    """TPR and FPR at the window level and the (run, firm) level ("ever flagged").

    ``labels``: a bool for everything, {run: bool}, {(run, firm): bool}, or a
    callable (run, firm) -> bool. True = colluding."""
    results = result if isinstance(result, list) else [result]
    win = {True: [0, 0], False: [0, 0]}     # label -> [flags, tests]
    unit = {True: [0, 0], False: [0, 0]}
    for res in results:
        for t in res.tests:
            y = _label(labels, t["run"], t["firm"])
            win[y][0] += t["flag"]
            win[y][1] += 1
        for (run, firm), r in res.first_flag.items():
            y = _label(labels, run, firm)
            unit[y][0] += r is not None
            unit[y][1] += 1
    rate = lambda c: c[0] / c[1] if c[1] else float("nan")
    return {"tpr_window": rate(win[True]), "fpr_window": rate(win[False]),
            "tpr_run": rate(unit[True]), "fpr_run": rate(unit[False]),
            "n_windows": {"pos": win[True][1], "neg": win[False][1]},
            "n_units": {"pos": unit[True][1], "neg": unit[False][1]}}
