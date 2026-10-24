"""Counterfactual replay, validated on scripted (stub) agents only."""
import numpy as np
import pytest

from testbed.metrics import observation_from_log, replay, replay_many
from testbed.metrics.synthetic import simulate, to_records
from testbed.types import Action

RECS = to_records(simulate(n_runs=1, n_rounds=30, policy="kbit", k=1, seed=5))
RUN = RECS[0]["run"]


class Reader:
    """Bids low on contract 0 when the rival's shown Val says 'low cost' (bit 1)."""
    def __init__(self, noise=0.0, rng=None):
        self.noise, self.rng = noise, rng or np.random.default_rng(0)

    def act(self, obs):
        v = obs.rivals_prebid[1 - obs.firm]["val"]
        b0 = None if v == 1 else 10.0
        bids = [b0] + [10.0 + self.noise * self.rng.standard_normal() for _ in range(3)]
        return Action(bids=bids)


class Ignorer(Reader):
    def act(self, obs):
        return Action(bids=[10.0 + self.noise * self.rng.standard_normal() for _ in range(4)])


def test_observation_from_log():
    obs = observation_from_log(RECS, RUN, 5, 0, override={1: {"val": 3}})
    assert obs.round == 5 and obs.phase == "bid" and len(obs.costs) == 4
    assert obs.rivals_prebid[1]["val"] == 3
    assert [h["round"] for h in obs.history] == [1, 2, 3, 4]


def _points():
    """Rounds where the stub's decision would change under some donor."""
    return [(RUN, t, 0) for t in range(2, 30)]


def test_reader_shows_flow_and_ignorer_does_not():
    rng = np.random.default_rng(1)
    reader = replay_many(RECS, "val", lambda r, t, f: Reader(), _points(), n_samples=3)
    ignorer = replay_many(RECS, "val", lambda r, t, f: Ignorer(0.5, rng), _points(), n_samples=8)
    # a changed decision moves one of four contracts by 1 (10 -> abstain = 11)
    changed = [x for x in reader["results"] if x.content_changed]
    assert changed and all(x.flow == pytest.approx(0.25) for x in changed)
    assert all(x.flow == 0 for x in reader["results"] if not x.content_changed)
    assert reader["flow"] > 0.1
    assert abs(ignorer["flow"]) < 0.1


def test_donor_has_different_rival_costs_and_fresh_agents():
    calls = []

    def factory(run, rnd, firm):
        calls.append((run, rnd, firm))
        return Reader()

    res = replay(RECS, 10, 0, "val", factory, n_samples=4)
    assert len(calls) == 3 * 4 and set(calls) == {(RUN, 10, 0)}
    by = {(r["round"], r["firm"]): r for r in RECS if r.get("type") == "round"}
    cq = lambda c: [(x - 1) * 4 // 12 for x in c]
    assert cq(by[(res.donor_round, 1)]["costs"]) != cq(by[(10, 1)]["costs"])
    assert res.original_bids.shape == (8, 4) and res.counterfactual_bids.shape == (4, 4)


def test_hidden_medium_is_rejected():
    with pytest.raises(ValueError):
        replay(RECS, 10, 0, "msg", lambda *a: Reader(), n_samples=2)
