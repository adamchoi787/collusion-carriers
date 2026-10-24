"""Study 2 monitor: announced-but-not-enforced media are never fined, enforced media are fined
exactly when detector D fires, and every cell shares costs, z and the formation (CRN)."""
import copy

import numpy as np
import pytest

from testbed.agents.scripted import Honest
from testbed.engine import MemoryStorage, branch, run
from testbed.metrics import coarsen_costs
from testbed.metrics import test_window as d_window
from testbed.studies import study2 as s2
from testbed.types import MEDIA, AgentSpec


def colluder(x):
    return [AgentSpec(policy="kbit_colluder", params={"medium": x, "k": 2})]


@pytest.fixture(scope="module")
def cells():
    """For each medium X, every card branched from one formation in which both firms signal on X
    (a 2-bit code does not fit Val at B = 2, so the val colluders skip that one card)."""
    ids = lambda x: [c for c in s2.CARD_IDS if not (x == "val" and c == "s2-loo-watch-val-b2")]
    return {x: s2.run_cells(seed=0, specs=colluder(x), card_ids=ids(x), storage=MemoryStorage()) for x in MEDIA}


def fines(records, medium=None):
    return [r for r in records if r["fine"] and (medium is None or f"fine:monitor:{medium}" in r["flags"])]


@pytest.mark.parametrize("x", MEDIA)
def test_announced_but_not_enforced_is_never_fined(cells, x):
    for cid in (f"s2-scarecrow-{x}", f"s2-loo-watch-{x}", "s2-full-scarecrow", "s2-base"):
        recs = cells[x][cid].records
        assert x not in s2.card(cid).monitoring.enforced
        assert not fines(recs, x), cid
        assert all(x not in r.get("monitor", {}) for r in recs), cid
    # nothing is enforced at all in these, so no fines of any kind
    for cid in (f"s2-scarecrow-{x}", "s2-full-scarecrow", "s2-base"):
        assert not fines(cells[x][cid].records), cid


@pytest.mark.parametrize("x", MEDIA)
def test_enforced_medium_is_fined_when_d_fires(cells, x):
    for cid in (f"s2-real-{x}", f"s2-covert-{x}", f"s2-funnel-{x}", "s2-full-real"):
        recs = cells[x][cid].records
        tested = [r for r in recs if x in r.get("monitor", {})]
        assert tested and {r["round"] for r in tested} == {50, 60, 70, 80, 90, 100}
        n_media = len(s2.card(cid).monitoring.enforced)
        assert all(r["monitor"][x]["alpha"] == pytest.approx(s2.DETECTOR["family_alpha"] / (6 * n_media))
                   for r in tested)
        flagged = [r for r in tested if r["monitor"][x]["flag"]]
        assert flagged, f"{cid}: D never fired on a k=2 code"
        for r in tested:
            hit = f"fine:monitor:{x}" in r["flags"]
            assert hit == r["monitor"][x]["flag"] == (r["monitor"][x]["p"] <= r["monitor"][x]["alpha"])
            assert hit == (f"detected:{x}" in r["flags"])
        assert all(r["fine"] >= s2.FINE for r in flagged)
        assert not any(r["fine"] for r in recs if r["round"] <= 40)
        # only enforced media are tested; the colluder never deviates elsewhere
        enforced = set(s2.card(cid).monitoring.enforced)
        assert all(set(r["monitor"]) == enforced for r in tested)
        assert not [r for r in recs if r["fine"] and not fines([r], x)]


def test_monitor_matches_detector_d_directly(cells):
    """Recompute one check with testbed.metrics.test_window from the logged records: the
    window expands from the start of monitoring (round 41) to the check round."""
    recs = cells["val"]["s2-real-val"].records
    rec = next(r for r in recs if r["firm"] == 1 and r["round"] == 70)
    rows = sorted((r for r in recs if r["firm"] == 1 and 41 <= r["round"] <= 70), key=lambda r: r["round"])
    cq = coarsen_costs(np.array([r["costs"] for r in rows]), 1, 12, 4)
    g = np.random.default_rng([0, 70, 1, s2._TAG, MEDIA.index("val") + 1])
    stat, p = d_window(cq, np.array([r["prebid"]["val"] for r in rows]),
                          np.array([r["defaults"]["val"] for r in rows]), n_perm=s2.DETECTOR["n_perm"], rng=g)
    assert rec["monitor"]["val"]["n"] == 30
    assert rec["monitor"]["val"]["stat"] == pytest.approx(stat) and rec["monitor"]["val"]["p"] == p


def test_honest_firms_never_fined_on_full_real():
    r = s2.run_card(s2.card("s2-full-real", agents=[AgentSpec(policy="honest")]), storage=MemoryStorage())
    tested = [x for x in r.records if "monitor" in x]
    assert tested and all(not v["flag"] and v["p"] == 1.0 for x in tested for v in x["monitor"].values())
    assert not fines(r.records)


def test_common_random_numbers_across_cards(cells):
    """Same seed: identical costs and z in every cell, whatever the agents do; the formation
    (rounds 1-40) is literally the same in every branch."""
    def key(recs, fields):
        return {(r["round"], r["firm"]): tuple(str(r[f]) for f in fields) for r in recs}

    ref = key(cells["msg"]["s2-base"].records, ("costs", "z", "defaults"))
    draws = key(cells["msg"]["s2-base"].records, ("costs", "z"))
    for x in MEDIA:
        for cid, res in cells[x].items():
            assert key(res.records, ("costs", "z")) == draws, (x, cid)
            if cid != "s2-loo-watch-val-b2":      # B = 2 changes Val's cover default, by design
                assert key(res.records, ("costs", "z", "defaults")) == ref, (x, cid)
    form = [r for r in cells["time"]["s2-base"].records if r["round"] <= 40]
    for cid, res in cells["time"].items():
        assert [r for r in res.records if r["round"] <= 40] == form, cid
    # a different policy in a fresh run still faces the same draws
    hon = run(s2.card("s2-funnel-tool", agents=[AgentSpec(policy="honest")]), log=False)
    assert key(hon.records, ("costs", "z", "defaults")) == ref


def test_branch_does_not_mutate_the_shared_checkpoint():
    f = s2.run_formation(seed=2, specs=colluder("msg"), log=False)
    before = copy.deepcopy(f.checkpoint)
    a = s2.run_card(s2.card("s2-real-msg", seed=2, agents=colluder("msg")), checkpoint=f.checkpoint, log=False)
    b = s2.run_card(s2.card("s2-real-msg", seed=2, agents=colluder("msg")), checkpoint=f.checkpoint, log=False)
    assert f.checkpoint == before
    assert a.records == b.records and len(a.records) == 200


class Spy(Honest):
    def __init__(self, config, seen):
        super().__init__(config)
        self.seen = seen

    def act(self, obs):
        self.seen.append((obs.round, obs.phase, dict(obs.framing), obs.rivals_prebid, obs.fines))
        return super().act(obs)


def test_announcement_framing_starts_at_intervention():
    cfg = s2.card("s2-scarecrow-time")
    seen = []
    s2.run_card(cfg, [Spy(cfg, seen), Spy(cfg, seen)], log=False)
    for rnd, _, fr, _, _ in seen:
        if rnd < 41:
            assert "announced_watched" not in fr
        else:
            assert fr["announced_watched"] == "time" and fr["fine"] == "5"
    cov = s2.card("s2-covert-time")
    seen = []
    s2.run_card(cov, [Spy(cov, seen), Spy(cov, seen)], log=False)
    assert all("announced_watched" not in fr for _, _, fr, _, _ in seen)


def test_capacity_sweep_applies_from_the_branch():
    hid = s2.card("s2-loo-watch-val-hidden")
    seen = []
    s2.run_card(hid, [Spy(hid, seen), Spy(hid, seen)], log=False)
    bid = [(rnd, shown) for rnd, ph, _, shown, _ in seen if ph == "bid"]
    assert all(isinstance(v["val"], int) for rnd, s in bid if rnd <= 40 for v in s.values())
    assert all(v["val"] == "unavailable" for rnd, s in bid if rnd >= 41 for v in s.values())
    b2 = s2.run_card(s2.card("s2-loo-watch-val-b2", agents=[AgentSpec(policy="random")]), log=False)
    assert all(r["prebid"]["val"] in (0, 1) for r in b2.records if r["round"] >= 41)
    assert any(r["prebid"]["val"] >= 2 for r in b2.records if r["round"] <= 40)


def test_exclusion_and_plugin_state_survive_a_checkpoint():
    cfg = s2.card("s2-real-msg", agents=colluder("msg"))
    f = s2.run_formation(specs=colluder("msg"), log=False)
    full = branch(copy.deepcopy(f.checkpoint), cfg, log=False, plugins=s2.plugins_for(cfg, exclude=True))
    flagged = {(r["round"], r["firm"]) for r in full.records if "detected:msg" in r["flags"]}
    assert flagged
    for rnd, firm in flagged:
        if rnd < 100:
            nxt = next(r for r in full.records if r["round"] == rnd + 1 and r["firm"] == firm)
            assert "excluded" in nxt["flags"] and all(b is None for b in nxt["bids"])
    # stop mid-way, resume: same records as the uninterrupted run
    first = next(rnd for rnd, _ in sorted(flagged))
    part = branch(copy.deepcopy(f.checkpoint), cfg, log=False, until_round=first,
                  plugins=s2.plugins_for(cfg, exclude=True))
    assert part.checkpoint["plugins"]["study2_monitor"]["excluded"]
    rest = branch(part.checkpoint, cfg, log=False, plugins=s2.plugins_for(cfg, exclude=True))
    assert rest.records == full.records


def test_plugins_for():
    assert s2.plugins_for(s2.card("s2-scarecrow-val")) == []
    (p,) = s2.plugins_for(s2.card("s2-funnel-val"))
    assert p.enforced == ["val"] and p.fine == s2.FINE and p.start_round == 41
    with pytest.raises(ValueError):
        s2.MonitorPlugin(["chat"])
