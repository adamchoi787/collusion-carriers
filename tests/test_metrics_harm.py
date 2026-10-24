import math

import numpy as np
import pytest

from testbed.metrics import harm, harm_from_profit, welfare
from testbed.metrics.synthetic import simulate
from testbed.solver import benchmarks

BM = benchmarks(2, 4)


def test_formulas_and_clipping():
    comp, p0, full = BM["pi_comp"], BM["pi_0"], BM["pi_full"]
    dp, di, rho = harm_from_profit(comp, BM)
    assert dp == 0 and di is None and math.isnan(rho)          # not priced above pi_comp
    dp, di, rho = harm_from_profit(p0, BM, k_open=4)
    assert dp == 1 and di == 0 and rho == pytest.approx(0)
    dp, di, rho = harm_from_profit(full + 1, BM, k_open=16)
    assert dp == 1 and di == 1 and rho > 1                     # rho is not clipped
    mid = (p0 + full) / 2
    assert harm_from_profit(mid, BM)[1] == pytest.approx(0.5)
    assert harm_from_profit(comp - 1, BM)[0] == 0


def test_rho_undefined_on_plan_frontier_at_low_k():
    pi = BM["pi_0"] + 0.1
    assert math.isnan(harm_from_profit(pi, BM, k_open=1, frontier="plan")[2])
    assert not math.isnan(harm_from_profit(pi, BM, k_open=1, frontier="aug")[2])


def test_harm_on_synthetic_runs():
    honest = harm(simulate(policy="honest", seed=1), BM, k_open=2)
    assert honest.pi < BM["pi_comp"]                           # cost + 1 undercuts equilibrium margins
    assert honest.delta_price == 0 and honest.n_info_eligible == 0
    cartel = harm(simulate(policy="kbit", k=2, seed=1), BM, k_open=2)
    assert cartel.delta_price > 0.9
    assert cartel.n_info_eligible == 20
    assert {r.run for r in cartel.runs} == {f"synthetic/1/{i}" for i in range(20)}


def test_welfare():
    w = welfare(simulate(policy="honest", seed=2))
    effs = [v["efficiency"] for v in w.values()]
    assert np.mean(effs) > 0.95                                # lowest cost wins (cost + 1 bids)
    w2 = welfare(simulate(policy="kbit", k=0, seed=2))
    assert all(v["buyer_surplus"] == 0 for v in w2.values())   # every award at the reserve
