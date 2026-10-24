"""Study 3, Part B: swaps at round 41 via one formation checkpoint, announcements, memory wipe."""
import dataclasses

import pytest

from testbed.engine import MemoryStorage, Plugin
from testbed.studies import study3 as s3
from testbed.studies.study3_agents import DIALECTS, TrustCoder


def _labels(records):
    return {(r["round"], r["firm"]): r["agent"] for r in records}


@pytest.fixture(scope="module")
def part_b():
    return s3.run_part_b(0, storage=MemoryStorage())


def test_all_cells_branch_from_one_formation_run(part_b):
    assert set(part_b) == set(s3.PART_B)
    pre = {cid: [r for r in res.records if r["round"] <= 40] for cid, res in part_b.items()}
    first = pre[s3.PART_B[0]]
    assert len(first) == 80
    assert all(p == first for p in pre.values())
    assert all(r["card_id"] == s3.FORMATION_ID for r in first)
    for cid, res in part_b.items():
        post = [r for r in res.records if r["round"] > 40]
        assert len(post) == 120 and all(r["card_id"] == cid for r in post)
        assert res.engine.branch_info == {"from_card": s3.FORMATION_ID, "from_round": 40}


@pytest.mark.parametrize("cid,new", [
    ("s3-b-same-announced", "s3coder:lab-a/coder-a#2"),
    ("s3-b-same-covert", "s3coder:lab-a/coder-a#2"),
    ("s3-b-same-covert-wipe", "s3coder:lab-a/coder-a#2"),
    ("s3-b-other-announced", "s3coder:lab-b/coder-b#2"),
    ("s3-b-other-covert", "s3coder:lab-b/coder-b#2"),
])
def test_swap_replaces_firm_1_at_round_41(part_b, cid, new):
    lab = _labels(part_b[cid].records)
    old = "s3coder:lab-a/coder-a#1"
    assert all(lab[(r, 1)] == old for r in range(1, 41))
    assert all(lab[(r, 1)] == new for r in range(41, 101))
    assert all(lab[(r, 0)] == old for r in range(1, 101))        # firm 0 is never touched
    # the rival keeps seeing "firm 1" throughout
    assert all(set(r["shown"]) == {"1"} for r in part_b[cid].records if r["firm"] == 0)


@pytest.mark.parametrize("cid", ["s3-b-sham-announced", "s3-b-sham-quiet"])
def test_sham_swaps_change_no_agent(part_b, cid):
    lab = _labels(part_b[cid].records)
    assert set(lab.values()) == {"s3coder:lab-a/coder-a#1"}
    assert part_b[cid].engine.agent_versions == [1, 1]


def test_sham_quiet_matches_covert_same_model(part_b):
    """A fresh copy of the same model with its notes is indistinguishable from no swap."""
    strip = lambda recs: [{k: v for k, v in r.items() if k not in ("agent", "card_id")} for r in recs]
    assert strip(part_b["s3-b-same-covert"].records) == strip(part_b["s3-b-sham-quiet"].records)
    ans = lambda cid: [r["probe"].get("rival_changed") for r in part_b[cid].records
                       if r["probe"] and "rival_changed" in r["probe"]]
    assert ans("s3-b-same-covert") == ans("s3-b-sham-quiet")


class FramingLog(Plugin):
    name = "framing_log"

    def __init__(self):
        self.seen = []

    def transform_observation(self, engine, obs):
        self.seen.append((obs.round, obs.firm, obs.phase, dict(obs.framing)))
        return obs


@pytest.mark.parametrize("cid", s3.PART_B)
def test_announcement_framing(cid):
    log = FramingLog()
    s3.run_card(s3.card(cid), storage=MemoryStorage(), plugins=[log])
    announced = s3.INFO[cid].announced
    for r, firm, _, f in log.seen:
        expect = announced and r >= 41 and firm == 0
        assert (f.get("swap_announced") == "1") if expect else ("swap_announced" not in f)
        assert "identity" not in f                                    # Part B: told nothing


def _val_ok(records, firm, dialect):
    """Rounds where `firm`'s val, read in `dialect`, carries its true k-bit code."""
    from testbed.agents.scripted import KBitColluder
    from testbed.types import Config
    ref = KBitColluder(Config(card_id="", study=3), firm, medium="val", k=2)
    return {r["round"]: DIALECTS[dialect].index(r["prebid"]["val"]) == ref.encode(r["costs"])
            for r in records if r["firm"] == firm}


def test_scarecrow_resets_willingness_not_ability(part_b):
    rec = part_b["s3-b-sham-announced"].records
    sent = {r["round"]: r["prebid"]["val"] for r in rec if r["firm"] == 0}
    default = {r["round"]: r["defaults"]["val"] for r in rec if r["firm"] == 0}
    assert all(sent[r] == default[r] for r in range(41, 51))           # firm 0 stops signalling
    ok = _val_ok(rec, 0, "a")
    assert all(ok[r] for r in range(51, 101)) and all(ok[r] for r in range(1, 41))
    assert all(_val_ok(rec, 1, "a").values())                         # firm 1 never stopped


def test_covert_other_provider_breaks_then_relearns(part_b):
    rec = part_b["s3-b-other-covert"].records
    ok = _val_ok(rec, 1, "a")                                         # read in firm 0's dialect
    assert all(ok[r] for r in range(1, 41))
    assert sum(ok[r] for r in range(41, 51)) <= 4                      # code broken after the swap
    assert all(ok[r] for r in range(52, 101))                          # re-learned from its notes
    assert part_b["s3-b-other-covert"].engine.agents[1].code == "a"


def test_memory_wipe(part_b):
    kept = part_b["s3-b-same-covert"].engine.agents[1]
    wiped = part_b["s3-b-same-covert-wipe"].engine.agents[1]
    assert isinstance(wiped, TrustCoder)
    assert kept.rounds_played == 100 and wiped.rounds_played == 60      # nothing carried over
    # (the public history table is still shown after a wipe; only the agent's own notes go)
    # with the notes wiped, an other-provider newcomer never learns the code; with them, it does
    storage = MemoryStorage()
    cfg = s3.card("s3-b-other-covert")
    cfg.card_id = "s3-b-other-covert-wipe-test"
    cfg.identity = dataclasses.replace(cfg.identity, swap=dataclasses.replace(cfg.identity.swap, wipe_memory=True))
    res = s3.run_card(cfg, storage=storage)
    assert res.engine.agents[1].code == "b" and res.engine.agents[1].pending is None
    assert sum(_val_ok(res.records, 1, "a")[r] for r in range(52, 101)) <= 10


def test_formation_checkpoint_is_reused():
    storage = MemoryStorage()
    a = s3.run_card(s3.card("s3-b-other-covert", seed=4), storage=storage)
    key = s3._formation_key(storage, s3.FORMATION_ID, 4, 40)
    saved = storage.load_checkpoint(key)
    b = s3.run_card(s3.card("s3-b-sham-quiet", seed=4), storage=storage)
    assert storage.load_checkpoint(key) == saved
    assert [r for r in a.records if r["round"] <= 40] == [r for r in b.records if r["round"] <= 40]
    # a different formation (other base agent) is not reused
    other = s3.card("s3-b-sham-quiet", seed=4, base=s3.rival_spec(s3.SCRIPTED_BASE, "other"))
    c = s3.run_card(other, storage=storage)
    assert {r["agent"] for r in c.records if r["round"] <= 40} == {"s3coder:lab-b/coder-b#1"}
