import numpy as np
import pytest

from testbed.solver import Market, analytic_equilibrium, benchmarks, exploitability, fictitious_play


@pytest.mark.parametrize("n_firms", [2, 3])
def test_analytic_equilibrium_has_no_profitable_deviation(n_firms):
    m = Market(n_firms=n_firms)
    eq = analytic_equilibrium(m)
    assert exploitability(eq, m.reserve, grid_step=0.0005) < 1e-9
    # intervals are ordered and contiguous, ending at the reserve
    assert np.all(np.diff(eq.lower) > 0)
    assert eq.upper[-1] == m.reserve
    np.testing.assert_allclose(eq.upper[:-1], eq.lower[1:])
    # every type earns a positive margin: bids stay above cost
    assert np.all(eq.lower > eq.types)


@pytest.mark.parametrize("n_firms", [2, 3])
def test_analytic_equilibrium_monte_carlo(n_firms):
    """Simulate the mixed strategies; realised profit matches the formula."""
    m = Market(n_firms=n_firms)
    eq = analytic_equilibrium(m)
    rng = np.random.default_rng(0)
    n = 400_000
    costs = rng.integers(m.cost_low, m.cost_high + 1, size=(n, n_firms))
    u = rng.random((n, n_firms))
    grid = np.linspace(0, 1, 20001)
    bids = np.full((n, n_firms), np.inf)
    for j, c in enumerate(eq.types):
        b = np.linspace(eq.lower[j], eq.upper[j], 20001)
        inv = np.interp(grid, eq.cdf(j, b), b)           # quantile function
        mask = costs == c
        bids[mask] = np.interp(u[mask], grid, inv)
    win = bids == bids.min(axis=1, keepdims=True)
    margin = np.where(win & np.isfinite(bids), bids - costs, 0.0)
    assert margin.sum(axis=1).mean() / n_firms == pytest.approx(eq.expected_profit_per_firm(), rel=0.01)


@pytest.mark.parametrize("n_firms", [2, 3])
def test_fictitious_play_converges_to_analytic(n_firms):
    m = Market(n_firms=n_firms)
    eq = analytic_equilibrium(m)
    short = fictitious_play(m, grid_step=0.1, iterations=2000)
    long = fictitious_play(m, grid_step=0.1, iterations=20000)
    assert long.exploitability < short.exploitability
    assert long.exploitability < 0.02
    assert long.profit_per_firm == pytest.approx(eq.expected_profit_per_firm(), abs=0.01)


def test_pi_comp_values():
    assert benchmarks(2, 4)["pi_comp"] == pytest.approx(4 * 1.7708333, abs=1e-6)
    assert benchmarks(3, 4)["pi_comp"] == pytest.approx(4 * 0.9635417, abs=1e-6)
