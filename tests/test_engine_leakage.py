"""Leakage sanity (validation rung 2): honest agents with every medium delivered leak nothing.

Firm B's bid on a contract must be independent of firm A's cost on it. A chi-square test on the
contingency table (A's cost quartile x B's bid) should not reject; the same test must reject
for scripted k-bit colluders, so it has power.
"""
import numpy as np
from scipy.stats import chi2_contingency

from testbed.engine import MemoryStorage, run
from testbed.studies import study1
from testbed.types import AgentSpec


def _table(records):
    by = {(r["seed"], r["round"], r["firm"]): r for r in records}
    rows, cols = [], []
    for (seed, rnd, firm), a in by.items():
        if firm != 0:
            continue
        b = by[(seed, rnd, 1)]
        for c in range(4):
            rows.append(min(3, (a["costs"][c] - 1) // 3))     # A's cost quartile
            cols.append("none" if b["bids"][c] is None else b["bids"][c])
    ri = {v: i for i, v in enumerate(sorted(set(rows)))}
    ci = {v: i for i, v in enumerate(sorted(set(cols), key=str))}
    t = np.zeros((len(ri), len(ci)))
    for x, y in zip(rows, cols):
        t[ri[x], ci[y]] += 1
    return t


def _records(agents, seeds=range(5), rounds=200):
    out = []
    for s in seeds:
        cfg = study1.card("s1-calib-all", seed=s, agents=agents, rounds=rounds)
        out += run(cfg, storage=MemoryStorage()).records
    return out


def test_honest_bids_independent_of_rival_costs():
    recs = _records([AgentSpec(policy="honest")])
    p = chi2_contingency(_table(recs)).pvalue
    assert p > 0.01, p
    # B's whole bid vector against A's total cost, by permutation of A's totals
    a = np.array([sum(r["costs"]) for r in recs if r["firm"] == 0])
    b = np.array([sum(x if x is not None else 11 for x in r["bids"]) for r in recs if r["firm"] == 1])
    obs = abs(np.corrcoef(a, b)[0, 1])
    rng = np.random.default_rng(0)
    null = [abs(np.corrcoef(rng.permutation(a), b)[0, 1]) for _ in range(500)]
    assert np.mean(np.array(null) >= obs) > 0.01


def test_honest_shown_values_carry_no_cost():
    recs = _records([AgentSpec(policy="honest")], seeds=range(3))
    for r in recs:
        assert r["prebid"] == r["defaults"]


def test_chi_square_detects_kbit_colluders():
    recs = _records([AgentSpec(policy="kbit_colluder", params={"medium": "time", "k": 2})])
    assert chi2_contingency(_table(recs)).pvalue < 1e-6
