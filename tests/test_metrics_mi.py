import numpy as np
import pytest

from testbed.metrics.mi import cmi, p_value, stratified_permutations


def test_cmi_exact_cases():
    rng = np.random.default_rng(0)
    x = rng.integers(4, size=20000)
    assert cmi(x, x, mm=False) == pytest.approx(2.0, abs=0.01)           # copy: H(X)
    assert cmi(x, rng.integers(4, size=20000)) == pytest.approx(0.0, abs=0.003)
    z = rng.integers(3, size=20000)
    y = (x + z) % 4
    assert cmi(x, y, mm=False) == pytest.approx(0.0, abs=0.01) or cmi(x, y) < 2
    assert cmi(x, y, z) == pytest.approx(2.0, abs=0.01)                    # only visible given z


def test_miller_madow_reduces_bias():
    rng = np.random.default_rng(1)
    plug, mm = [], []
    for _ in range(200):
        x, y, z = rng.integers(4, size=(3, 300))
        plug.append(cmi(x, y, z, mm=False))
        mm.append(cmi(x, y, z))
    assert abs(np.mean(mm)) < abs(np.mean(plug)) / 2


def test_batched_permutations_match_loop():
    rng = np.random.default_rng(2)
    x, y, z = rng.integers(3, size=(3, 200))
    idx = stratified_permutations(z, 20, rng)
    batch = cmi(x[idx], y, z)
    loop = [cmi(x[i], y, z) for i in idx]
    np.testing.assert_allclose(batch, loop)


def test_stratified_permutations_stay_in_strata():
    rng = np.random.default_rng(3)
    strata = rng.integers(5, size=300)
    idx = stratified_permutations(strata, 50, rng)
    assert (strata[idx] == strata[None, :]).all()
    assert all(sorted(row) == list(range(300)) for row in idx[:5])
    assert (idx != np.arange(300)).any(axis=1).all()


def test_p_value():
    assert p_value(1.0, np.zeros(99)) == pytest.approx(0.01)
    assert p_value(0.0, np.zeros(99)) == 1.0
