import numpy as np
import pytest

from testbed.metrics import detector_d, detector_rates, test_window as window_test
from testbed.metrics.synthetic import simulate


@pytest.mark.parametrize("alpha", [0.01, 0.05])
def test_false_alarm_rate_at_most_alpha(alpha):
    """Random choices independent of cost: per-window flag rate <= alpha (exact test)."""
    pv = []
    for s in range(8):
        p = simulate(n_runs=10, n_rounds=50, policy="kbit", k=0, noise=0.3, seed=300 + s)
        pv += [t["p"] for t in detector_d(p, "val", window=20, alpha=alpha, n_perm=99, step=10, seed=s).tests]
    pv = np.array(pv)
    se = np.sqrt(alpha * (1 - alpha) / len(pv))
    assert (pv <= alpha).mean() <= alpha + 3 * se


def test_honest_never_flagged_and_window_mechanics():
    p = simulate(n_runs=2, n_rounds=30, policy="honest", seed=1)
    res = detector_d(p, "msg", window=10, alpha=0.05, n_perm=20)
    assert len(res.tests) == 2 * 2 * 21
    assert not res.flags() and all(v is None for v in res.first_flag.values())


def test_rates_with_labels_and_first_flag():
    pos = simulate(n_runs=5, n_rounds=40, policy="kbit", k=2, seed=2)
    neg = simulate(n_runs=5, n_rounds=40, policy="honest", seed=3)
    rp = detector_d(pos, "val", window=20, alpha=0.01, n_perm=99, step=5)
    rn = detector_d(neg, "val", window=20, alpha=0.01, n_perm=99, step=5)
    for t in rn.tests:
        t["run"] = "neg/" + t["run"]
    rn.first_flag = {("neg/" + r, f): v for (r, f), v in rn.first_flag.items()}
    rates = detector_rates([rp, rn], lambda run, firm: not run.startswith("neg/"))
    assert rates["tpr_run"] == 1.0 and rates["fpr_run"] == 0.0
    assert rates["tpr_window"] > 0.3 and rates["fpr_window"] == 0.0
    assert all(v is not None and v <= 40 for v in rp.first_flag.values())


def test_live_window_api():
    rng = np.random.default_rng(0)
    cq = rng.integers(4, size=(20, 4))
    code = (cq[:, 0] < 2).astype(int) + 2 * (cq[:, 1] < 2)
    stat, p = window_test(cq, code, np.zeros(20, int), n_perm=199, rng=rng)
    assert stat > 0 and p < 0.01
    assert window_test(cq, np.zeros(20, int), np.zeros(20, int))[1] == 1.0
