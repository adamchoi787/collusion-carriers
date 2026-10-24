import itertools

import numpy as np
import pytest

from testbed.solver import Market, benchmarks, best_zero_bit
from testbed.solver.zero_bit import search_ladder, search_split


def split_value(m: Market, t: int) -> float:
    sup, r = list(m.support), m.reserve
    tot = 0.0
    for p in itertools.product(sup, repeat=m.n_firms):
        part = [c for c in p if c <= t]
        if part:
            tot += r - sum(part) / len(part)
    return tot / len(sup) ** m.n_firms


@pytest.mark.parametrize("n_firms,t_best", [(2, 7), (3, 6)])
def test_split_threshold_is_best_and_exact(n_firms, t_best):
    m = Market(n_firms=n_firms)
    s = search_split(m)
    assert s.params["t"] == t_best
    assert s.contract_value == pytest.approx(max(split_value(m, t) for t in range(0, 11)))
    # t = r reproduces the plan's 0-bit point
    assert split_value(m, 10) == pytest.approx(benchmarks(n_firms, 1)["pi_star"][0] * n_firms)


@pytest.mark.parametrize("n_firms", [2, 3])
def test_pi0_winner_and_family(n_firms):
    bm = benchmarks(n_firms, 4)
    assert bm["pi_0_scheme"]["name"] == "split"
    names = {s["name"] for s in bm["pi_0_family"]}
    assert {"split", "asym", "rotation"} <= names
    assert max(s["value"] for s in bm["pi_0_family"]) == pytest.approx(bm["pi_0"])


def test_rotation_with_backup_needs_a_bid_grid():
    w, members = best_zero_bit(Market(2), 4, bid_step=1.0)
    assert {"priority", "ladder"} <= {s.name for s in members}


def test_ladder_approaches_full_information_as_bid_step_shrinks():
    m = Market(2)
    vals = [search_ladder(m, step).contract_value for step in (1.0, 0.5, 0.1, 0.01)]
    assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))
    full = benchmarks(2, 1)["pi_full"] * 2
    assert vals[-1] > 0.97 * full   # three levels already recover most of it
