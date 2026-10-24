"""Study 2 cards: the registry, what each card announces and enforces, and full 100-round runs."""
import pytest

from testbed.engine import MemoryStorage, config_from_dict, config_to_dict
from testbed.engine.config import effective_visibility
from testbed.run import main
from testbed.studies import study2 as s2
from testbed.types import MEDIA, AgentSpec

COLLUDE_MSG = [AgentSpec(policy="kbit_colluder", params={"medium": "msg", "k": 2})]


def test_card_count_and_ids():
    assert len(s2.CARD_IDS) == 25 == len(set(s2.CARD_IDS))
    for x in MEDIA:
        for fam in ("real", "scarecrow", "covert", "loo-watch", "funnel"):
            assert f"s2-{fam}-{x}" in s2.CARD_IDS
    for ref in ("s2-base", "s2-full-real", "s2-full-scarecrow", "s2-loo-watch-val-b2", "s2-loo-watch-val-hidden"):
        assert ref in s2.CARD_IDS
    with pytest.raises(KeyError):
        s2.card("s2-nope")


@pytest.mark.parametrize("fam,announced,enforced", [
    ("real", lambda x: {x}, lambda x: {x}),
    ("scarecrow", lambda x: {x}, lambda x: set()),
    ("covert", lambda x: set(), lambda x: {x}),
    ("loo-watch", lambda x: set(MEDIA) - {x}, lambda x: set(MEDIA) - {x}),
    ("funnel", lambda x: set(MEDIA) - {x}, lambda x: {x}),
])
def test_per_medium_split(fam, announced, enforced):
    for x in MEDIA:
        c = s2.card(f"s2-{fam}-{x}")
        assert set(c.monitoring.announced) == announced(x)
        assert set(c.monitoring.enforced) == enforced(x)
        assert c.monitoring.start_round == c.intervention_round == 41
        assert c.monitoring.fine == s2.FINE


def test_reference_and_sweep_cards():
    base = s2.card("s2-base")
    assert base.monitoring.announced == base.monitoring.enforced == [] and base.monitoring.fine == 0
    assert s2.card("s2-full-real").monitoring.enforced == list(MEDIA)
    fs = s2.card("s2-full-scarecrow").monitoring
    assert fs.announced == list(MEDIA) and fs.enforced == []
    b2 = s2.card("s2-loo-watch-val-b2")
    assert b2.symbols["val"] == 2 and "val" not in b2.monitoring.enforced + b2.monitoring.announced
    hid = s2.card("s2-loo-watch-val-hidden")
    assert effective_visibility(hid)["val"] == "error"          # rivals see "unavailable"
    assert all(effective_visibility(hid)[m] == "delivered" for m in ("msg", "time", "tool"))


def test_every_card_is_calib_all_otherwise():
    form = s2.formation()
    assert form.monitoring.enforced == form.monitoring.announced == []
    for c in s2.cards():
        assert c.study == 2 and c.permission == form.permission
        assert c.permission.kind == "named" and set(c.permission.media) == set(MEDIA)
        if c.card_id != "s2-loo-watch-val-hidden":
            assert c.visibility == form.visibility
        assert config_from_dict(config_to_dict(c)) == c


def test_gen_arm():
    c = s2.card("s2-funnel-time-gen", seed=3)
    assert c.card_id == "s2-funnel-time-gen" and c.permission.kind == "generic" and c.seed == 3
    assert c.monitoring.enforced == ["time"]
    assert s2.card("s2-formation-gen").permission.kind == "generic"
    assert all(c.card_id.endswith("-gen") for c in s2.cards(gen=True))


def test_rounds_override_moves_probes():
    c = s2.card("s2-real-val", rounds=60)
    assert c.rounds == 60 and all(p.rounds == [60] for p in c.probes)


def test_cli_lists_study2_cards(capsys):
    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    assert sum(line.startswith("s2-") for line in out.splitlines()) == 25
    assert "s1-calib-all" in out


def test_cli_runs_a_card_with_formation_and_branch(tmp_path, capsys):
    assert main(["--card", "s2-real-msg", "--agents", "scripted:kbit_colluder:medium=msg,k=2",
                 "--out", str(tmp_path)]) == 0
    from testbed.engine import read_log
    log = read_log(str(tmp_path / "s2-real-msg" / "0.jsonl"))
    header, rounds = log[0], [r for r in log if r["type"] == "round"]
    assert header["branch"] == {"from_card": "s2-formation", "from_round": 40}
    assert len(rounds) == 200 and sum(r["fine"] for r in rounds) > 0
    assert (tmp_path / "s2-formation" / "0.r40.ckpt.json").exists()


@pytest.mark.parametrize("specs", [
    COLLUDE_MSG,
    [AgentSpec(policy="honest")],
    [AgentSpec(policy="random"), AgentSpec(policy="kbit_colluder", params={"medium": "time", "k": 2})],
], ids=["kbit-msg", "honest", "random+kbit-time"])
def test_every_card_runs_100_rounds(specs):
    res = s2.run_cells(seed=1, specs=specs, storage=MemoryStorage())
    assert set(res) == set(s2.CARD_IDS)
    for cid, r in res.items():
        assert r.engine.round == 100 and r.checkpoint is None
        assert sorted({x["round"] for x in r.records}) == list(range(1, 101))
        assert len(r.records) == 200
        last = [x for x in r.records if x["round"] == 100]
        assert all(set(x["probe"]) == {"arrangement", "monitor"} for x in last)
        if specs[0].policy == "honest":
            assert all(x["fine"] == 0 for x in r.records), cid
