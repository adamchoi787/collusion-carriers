"""Determinism, common random numbers, auction rules, input validation, config round trips."""
import numpy as np
import pytest

from testbed.engine import MemoryStorage, config_from_yaml, config_to_yaml, run
from testbed.engine import rng
from testbed.engine.cover import defaults
from testbed.engine.framing import framing
from testbed.studies import study1
from testbed.types import MEDIA, Action, AgentSpec, Config, Permission

HONEST = [AgentSpec(policy="honest")]


def _run(cfg, agents=None):
    return run(cfg, agents, storage=MemoryStorage()).records


def test_same_seed_same_records():
    cfg = study1.card("s1-calib-all", seed=3, agents=[AgentSpec(policy="random")], rounds=30)
    a, b = _run(cfg), _run(cfg)
    assert a == b
    assert a != _run(study1.card("s1-calib-all", seed=4, agents=[AgentSpec(policy="random")], rounds=30))


def test_costs_and_z_are_common_random_numbers():
    seen = {}
    for cid in study1.CARD_IDS:
        cfg = study1.card(cid, seed=7, agents=[AgentSpec(policy="random")], rounds=20)
        recs = _run(cfg)
        seen[cid] = [(r["round"], r["firm"], r["costs"], r["z"]) for r in recs]
    first = next(iter(seen.values()))
    assert all(v == first for v in seen.values())
    for rnd, firm, costs, z in first:
        g = np.random.default_rng([7, rnd, firm])
        assert costs == list(g.integers(1, 13, size=4)) and z == g.integers(0, 4)


def test_costs_do_not_depend_on_agents():
    cfg = study1.card("s1-calib-all", seed=1, rounds=25)
    cfg.agents = HONEST
    a = [(r["costs"], r["z"]) for r in _run(cfg)]
    cfg.agents = [AgentSpec(policy="kbit_colluder", params={"medium": "msg", "k": 2})]
    b = [(r["costs"], r["z"]) for r in _run(cfg)]
    assert a == b


def test_cover_defaults():
    assert [defaults(z, {m: 4 for m in MEDIA}, 4)["msg"] for z in range(4)] == [0, 1, 2, 3]
    sym = {"msg": 4, "val": 2, "time": 4, "tool": 4}
    assert [defaults(z, sym, 4)["val"] for z in range(4)] == [0, 0, 1, 1]
    sym["val"] = 8
    assert [defaults(z, sym, 4)["val"] for z in range(4)] == [1, 3, 5, 7]
    sym["val"] = 101
    assert [defaults(z, sym, 4)["val"] for z in range(4)] == [12, 37, 63, 88]


class Fixed:
    def __init__(self, prebid=None, bids=None):
        self.prebid, self.bids = prebid, bids

    def act(self, obs):
        if obs.phase == "prebid":
            return Action(prebid=self.prebid)
        if obs.phase == "bid":
            return Action(bids=self.bids)
        return Action()

    def snapshot(self):
        return {}

    def restore(self, s):
        pass


def test_auction_lowest_bid_at_or_below_reserve_wins_at_its_bid():
    cfg = Config(card_id="t", study=0, rounds=1)
    recs = _run(cfg, [Fixed(bids=[5, 11, None, 7]), Fixed(bids=[6, 10, 3, 7])])
    a, b = recs
    assert a["winner"][:3] == [0, 1, 1]
    assert a["price"][:3] == [5, 10, 3]
    assert a["profit"] == pytest.approx(5 - a["costs"][0] + (7 - a["costs"][3] if a["winner"][3] == 0 else 0))
    assert b["won"] == [w == 1 for w in a["winner"]]


def test_no_bid_at_or_below_reserve_means_no_winner():
    recs = _run(Config(card_id="t", study=0, rounds=1), [Fixed(bids=[11] * 4), Fixed(bids=None)])
    assert recs[0]["winner"] == [None] * 4 and recs[0]["profit"] == 0


def test_ties_broken_by_seeded_rng_and_reproducible():
    cfg = Config(card_id="t", study=0, rounds=200)
    agents = lambda: [Fixed(bids=[10] * 4), Fixed(bids=[10] * 4)]
    recs = _run(cfg, agents())
    wins = [w for r in recs if r["firm"] == 0 for w in r["winner"]]
    assert 0.4 < np.mean(wins) < 0.6
    assert recs == _run(cfg, agents())
    for r in recs[:10]:
        assert r["winner"][2] == [0, 1][rng.tie_break(0, r["round"], 2, 2)]


def test_invalid_prebid_and_bids_fall_back_and_are_flagged():
    cfg = Config(card_id="t", study=0, rounds=1)
    recs = _run(cfg, [Fixed(prebid={"msg": 9, "val": "x", "time": 2.0}, bids=[-1, "a", 3]),
                      Fixed(prebid=None, bids=None)])
    a, b = recs
    assert a["prebid"]["msg"] == a["defaults"]["msg"] and a["prebid"]["time"] == 2
    assert {"invalid_prebid:msg", "invalid_prebid:val", "invalid_prebid:tool",
            "invalid_bid:0", "invalid_bid:1", "bad_bid_count"} <= set(a["flags"])
    assert a["bids"] == [None, None, 3, None]
    assert b["prebid"] == b["defaults"] and "no_prebid" in b["flags"]


def test_log_has_contract_fields():
    st = MemoryStorage()
    cfg = study1.card("s1-calib-time", seed=0, agents=HONEST, rounds=3)
    run(cfg, storage=st)
    lines = st.records("s1-calib-time", 0)
    assert lines[0]["type"] == "header" and {"config", "git_sha", "started"} <= set(lines[0])
    keys = {"type", "round", "firm", "z", "costs", "defaults", "prebid", "shown", "messages_sent", "bids",
            "won", "price", "profit", "fine", "flags", "probe", "usage"}
    assert len(lines) == 1 + 3 * 2
    for rec in lines[1:]:
        assert keys <= set(rec)
    assert lines[-1]["probe"] == {"arrangement": "no"} and lines[1]["probe"] is None


@pytest.mark.parametrize("cid", study1.CARD_IDS)
def test_yaml_round_trip(cid):
    cfg = study1.card(cid, seed=5, agents=[AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 1})])
    assert config_from_yaml(config_to_yaml(cfg)) == cfg


def test_yaml_rejects_unknown_fields():
    with pytest.raises(ValueError):
        config_from_yaml("card_id: x\nstudy: 1\nvisibilty: {}\n")


def test_framing_is_facts_only():
    cfg = study1.card("s1-decoy-loi-time")
    f = framing(cfg, 0, 1)
    assert f == {"permission": "named:private_message", "private_message": "true"}
    cfg.permission = Permission("forbid")
    cfg.monitoring.announced = ["val"]
    cfg.monitoring.fine = 5.0
    assert framing(cfg, 0, 41) == {"permission": "forbid", "announced_watched": "val", "fine": "5"}
    assert "announced_watched" not in framing(cfg, 0, 40)
    assert framing(study1.card("s1-free-chat"), 0, 1) == {"permission": "generic", "free_chat": "true"}


def test_framing_keys_are_ones_the_llm_agent_renders():
    from testbed.agents.prompts import FRAMING_KEYS
    from testbed.types import Identity, Role, Swap
    cfg = study1.card("s1-none-decoy")
    cfg.n_firms, cfg.free_chat = 3, True
    cfg.role = Role(told="auditor")
    cfg.identity = Identity(told="same", swap=Swap(announced=True, firm=1))
    cfg.monitoring.announced, cfg.monitoring.fine = ["msg"], 1.0
    assert set(framing(cfg, 0, 50)) <= set(FRAMING_KEYS)


def test_rules_carry_game_parameters():
    seen = []

    class Spy(Fixed):
        def act(self, obs):
            seen.append(obs.rules)
            return super().act(obs)

    cfg = Config(card_id="t", study=0, rounds=1, reserve=9)
    _run(cfg, [Spy(bids=None), Spy(bids=None)])
    assert seen[0]["reserve"] == 9 and seen[0]["symbols"]["val"] == 4 and seen[0]["rounds"] == 1


def test_three_firms_and_role_framing():
    from testbed.types import Role
    cfg = study1.card("s1-calib-all", seed=2, rounds=20,
                      agents=[AgentSpec(policy="kbit_colluder", params={"medium": "msg", "k": 2})])
    cfg.n_firms = 3
    cfg.role = Role(told="maybe_auditor", actual="undercover")
    recs = _run(cfg)
    assert len(recs) == 60
    assert all(set(r["shown"]) == {str(j) for j in range(3) if j != r["firm"]} for r in recs)
    assert all(sum(r["won"][c] for r in recs if r["round"] == 5) <= 1 for c in range(4))
    assert framing(cfg, 0, 1)["role_told"] == "maybe_auditor" and framing(cfg, 0, 1)["role_subject"] == "2"
    assert "role_told" not in framing(cfg, 2, 1)
