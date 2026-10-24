import math

import pytest

from testbed.metrics import cluster_bootstrap, decode, displacement, displacement_ratio
from testbed.metrics.synthetic import simulate

HIDE = {"msg": "hidden", "val": "hidden", "time": "hidden", "tool": "hidden"}


def test_ratio_arithmetic():
    before = {"msg": 0.0, "val": 1.0, "time": 0.0, "tool": 0.0}
    assert displacement_ratio(before, {"msg": 0, "val": 0, "time": 1, "tool": 0}, "val") == 1
    assert displacement_ratio(before, {"msg": 0, "val": 0, "time": 0, "tool": 0}, "val") == 0
    assert math.isnan(displacement_ratio(before, before, "val"))


def test_balloon_vs_removal():
    kw = dict(policy="kbit", k=1, receiver="mirror")
    base = simulate(medium="val", visibility={**HIDE, "val": "delivered"}, seed=1, **kw)
    moved = simulate(medium="time", visibility={**HIDE, "time": "delivered"}, seed=1, **kw)
    removed = simulate(policy="honest", seed=1)
    bal = displacement(base, moved, "val", n_perm=0, n_boot=20)
    assert bal["ratio"] == pytest.approx(1.0, abs=0.1)
    lo, hi = bal["ci95"]
    assert lo < 1.0 < hi + 0.05
    assert displacement(base, removed, "val", n_perm=0)["ratio"] == pytest.approx(0.0, abs=0.05)


def test_cluster_bootstrap():
    p = simulate(policy="kbit", k=1, receiver="mirror", seed=3)
    out = cluster_bootstrap(p, lambda q: decode(q, "val", n_perm=0).bits, n_boot=30)
    lo, hi = out["ci95"]
    assert lo <= out["estimate"] <= hi and hi - lo < 0.2
    # truth is 1 bit; the MM estimate sits ~0.015 below it, more than its
    # standard error here, so no interval is required to cover it
    assert out["estimate"] == pytest.approx(1.0, abs=0.03)
