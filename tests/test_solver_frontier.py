"""Rung 1 of the validation ladder: the solver reproduces the plan's numbers."""
import itertools
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from testbed.solver import (Market, benchmarks, best_partition, frontier_table, full_info_value,
                            per_contract_frontier, r90)

ROOT = Path(__file__).resolve().parents[1]


def brute_force_contract(m: Market, thresholds) -> float:
    """analysis/frontier.py's enumeration, generalised to N firms."""
    sup, r = list(m.support), m.reserve
    b = lambda c: sum(c > t for t in thresholds)
    tot = 0.0
    for prof in itertools.product(sup, repeat=m.n_firms):
        elig = [c for c in prof if c <= r]
        if not elig:
            continue
        low = min(b(c) for c in elig)
        tied = [c for c in elig if b(c) == low]
        tot += r - sum(tied) / len(tied)
    return tot / len(sup) ** m.n_firms


@pytest.mark.parametrize("k_bits,share", [(2, 0.379), (4, 0.758), (6, 0.848), (8, 0.939)])
def test_plan_k4_n2_info_shares(k_bits, share):
    rows = {r["bits"]: r for r in frontier_table(benchmarks(2, 4, 1, 12, 10))}
    assert rows[k_bits]["info_share"] == pytest.approx(share, abs=5e-4)


@pytest.mark.parametrize("k_bits,share", [(1, 0.758), (2, 0.939), (3, 0.988)])
def test_frontier_py_one_contract(k_bits, share):
    rows = {r["bits"]: r for r in frontier_table(benchmarks(2, 1, 1, 12, 10))}
    assert rows[k_bits]["info_share"] == pytest.approx(share, abs=5e-4)


def test_plan_r90_is_8_bits():
    bm = benchmarks(2, 4, 1, 12, 10)
    assert r90(bm) == 8
    assert 7 < r90(bm, interpolate=True) < 8


@pytest.mark.parametrize("n_firms", [2, 3])
@pytest.mark.parametrize("k", [0, 1, 2])
def test_dp_matches_brute_force(n_firms, k):
    m = Market(n_firms=n_firms)
    best = max(brute_force_contract(m, t) for t in itertools.combinations(list(m.support)[:-1], 2**k - 1))
    v, thr, _ = best_partition(m, 2**k, "plan")
    assert v == pytest.approx(best, abs=1e-12)
    assert brute_force_contract(m, thr) == pytest.approx(v, abs=1e-12)


@pytest.mark.parametrize("n_firms", [2, 3])
def test_full_info(n_firms):
    m = Market(n_firms=n_firms)
    sup, r = list(m.support), m.reserve
    direct = np.mean([r - min(c for c in p if c <= r) if min(p) <= r else 0.0
                      for p in itertools.product(sup, repeat=n_firms)])
    assert full_info_value(m) == pytest.approx(direct)
    pk = per_contract_frontier(m)
    assert pk[max(pk)] == pytest.approx(direct)          # 4 bits separate all 12 costs


@pytest.mark.parametrize("n_firms", [2, 3])
def test_frontier_shape(n_firms):
    bm = benchmarks(n_firms, 4)
    for fam in ("pi_star", "pi_star_aug", "pi_star_joint"):
        vals = [bm[fam][b] for b in sorted(bm[fam])]
        assert all(b2 >= b1 - 1e-12 for b1, b2 in zip(vals, vals[1:])), fam
        assert vals[-1] == pytest.approx(bm["pi_full"])
    for b in bm["pi_star"]:
        assert bm["pi_star_aug"][b] >= bm["pi_star"][b] - 1e-12
        assert bm["pi_star_joint"][b] >= bm["pi_star"][b] - 1e-12
    # the participation-augmented frontier starts at the best 0-bit scheme
    assert bm["pi_star_aug"][0] == pytest.approx(bm["pi_0"])
    assert bm["pi_comp"] < bm["pi_star"][0] < bm["pi_0"] < bm["pi_full"]


def test_plan_frontier_is_dominated_by_pi0_at_low_k():
    """Documented caveat: own-cost participation beats the plan's 1- and 2-bit schemes."""
    bm = benchmarks(2, 4)
    assert bm["pi_star"][1] < bm["pi_0"] and bm["pi_star"][2] < bm["pi_0"]
    assert bm["pi_star"][3] > bm["pi_0"]


def test_joint_codes_beat_integer_allocation_at_6_bits():
    bm = benchmarks(2, 4)
    assert bm["pi_star_joint"][6] > bm["pi_star"][6] + 1e-3
    assert bm["allocation_joint"][6] == (3, 3, 3, 2)


def test_units_per_firm_per_round():
    bm2, bm1 = benchmarks(2, 4), benchmarks(2, 1)
    assert bm2["pi_full"] == pytest.approx(4 * bm1["pi_full"])
    assert bm1["pi_full"] == pytest.approx(full_info_value(Market(2)) / 2)


def test_frontier_script_runs():
    out = subprocess.run([sys.executable, str(ROOT / "analysis" / "frontier.py")],
                         capture_output=True, text=True, check=True).stdout
    assert "8 bits: info-dependent share 93.9%" in out
    assert "k=1 bits: share of full 95.0%, info-dependent share 75.8%" in out
