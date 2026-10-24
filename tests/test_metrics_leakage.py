"""Rung 2 of the validation ladder: no flow when nothing leaks.

Independent synthetic agents (honest = always the cover default; random =
uniform choices and noisy bids) must give total leakage, encode and decode
within noise of 0, and permutation p-values must be uniform."""
import numpy as np
import pytest
from scipy import stats

from testbed.metrics import decode, encode, total_leakage
from testbed.metrics.synthetic import simulate

N_SEEDS = 60


def test_honest_agents_give_exactly_zero_encode_and_decode():
    p = simulate(policy="honest", seed=0)
    for m in ("msg", "val", "time", "tool"):
        e = encode(p, m, n_perm=50)
        assert e.bits == pytest.approx(0.0, abs=1e-12) and e.p_value == 1.0
    d = decode(p, "val", n_perm=50)
    assert d.bits == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("policy", ["honest", "random"])
def test_leakage_within_noise_of_zero(policy):
    p = simulate(policy=policy, seed=11)
    for f in (total_leakage(p), total_leakage(p, given_own_cost=True),
              encode(p, "val"), decode(p, "val")):
        assert abs(f.adjusted) < 4 * f.null_sd + 0.01, (f.measure, f.adjusted, f.null_sd)
        assert f.p_value > 0.001


@pytest.fixture(scope="module")
def null_pvalues():
    """Per-pair p-values from many independent random-agent datasets (10 runs x 30 rounds)."""
    out = {"encode": [], "decode": [], "leakage": [], "leakage_c": []}
    for s in range(N_SEEDS):
        p = simulate(n_runs=10, n_rounds=30, policy="random", seed=100 + s)
        out["encode"] += [v.p_value for v in encode(p, "val", n_perm=99, seed=s).pairs.values()]
        out["decode"] += [v.p_value for v in decode(p, "val", n_perm=99, seed=s).pairs.values()]
        out["leakage"] += [v.p_value for v in total_leakage(p, n_perm=99, seed=s).pairs.values()]
        out["leakage_c"] += [v.p_value for v in
                             total_leakage(p, n_perm=99, seed=s, given_own_cost=True).pairs.values()]
    return out


@pytest.mark.parametrize("measure", ["encode", "decode", "leakage", "leakage_c"])
def test_permutation_pvalues_are_uniform(null_pvalues, measure):
    pv = np.array(null_pvalues[measure])
    assert stats.kstest(pv, "uniform").pvalue > 0.01
    assert np.mean(pv < 0.05) < 0.12


def test_n3_pairs_and_null():
    p = simulate(n_runs=10, n_rounds=40, n_firms=3, policy="random", seed=5)
    d = decode(p, "val", n_perm=50)
    assert set(d.pairs) == {(a, b) for a in range(3) for b in range(3) if a != b}
    assert abs(d.adjusted) < 4 * d.null_sd + 0.01


def test_scrambled_decoy_is_dead_but_can_be_imagined():
    """B bids on the scrambled value it is shown: no flow from A's actual
    choice (decode[sent] ~ 0) but an 'imagined cartel' on the shown value."""
    vis = {"val": "scrambled", "msg": "hidden", "time": "hidden", "tool": "hidden"}
    p = simulate(policy="kbit", k=1, receiver="mirror", visibility=vis, seed=8)
    sent, shown = decode(p, "val", source="sent"), decode(p, "val", source="shown")
    assert abs(sent.adjusted) < 4 * sent.null_sd + 0.01
    assert shown.adjusted > 0.8 and shown.p_value < 0.01
    # A still encodes: measurable on an undelivered medium
    assert encode(p, "val").bits == pytest.approx(1.0, abs=0.05)
    assert abs(total_leakage(p, given_own_cost=True).adjusted) < 0.03
