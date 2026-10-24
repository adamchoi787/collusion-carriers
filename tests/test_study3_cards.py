"""Study 3 cards: the registry, the Calib-Val setting, probes, composition, CLI and job building."""
import json

import pytest

from testbed import run as cli
from testbed.engine import MemoryStorage, config_from_dict, config_to_dict
from testbed.studies import study3 as s3
from testbed.types import MEDIA, AgentSpec


def test_nineteen_cards():
    assert len(s3.CARD_IDS) == len(set(s3.CARD_IDS)) == 19
    assert (len(s3.PART_A), len(s3.ZERO), len(s3.PART_B)) == (9, 3, 7)
    assert set(s3.TIER) == set(s3.CARD_IDS)
    told = {(s3.INFO[c].actual, s3.INFO[c].told) for c in s3.PART_A}
    assert told == {(a, t) for a in s3.ACTUALS for t in ("same", "different", None)}
    grid = {(s3.INFO[c].swap, s3.INFO[c].announced, s3.INFO[c].wipe) for c in s3.PART_B}
    assert grid == {(s, a, False) for s in ("none", "same_model", "other_provider") for a in (True, False)} | {
        ("same_model", False, True)}


def test_cli_lists_study3(capsys):
    assert cli.main(["--list"]) == 0
    out = capsys.readouterr().out
    for cid in s3.CARD_IDS:
        assert f"{cid}\tcore" in out


@pytest.mark.parametrize("cid", s3.CARD_IDS)
def test_every_card_runs_100_rounds_with_scripted_agents(cid):
    cfg = s3.card(cid, seed=3)
    assert cfg.study == 3 and cfg.rounds == 100 and cfg.n_firms == 2 and not cfg.free_chat
    res = s3.run_card(cfg, storage=MemoryStorage())
    assert res.engine.round == 100
    rounds = sorted({r["round"] for r in res.records})
    assert rounds == list(range(1, 101))
    assert len(res.records) == 200
    assert all(not r["flags"] for r in res.records)


@pytest.mark.parametrize("cid", s3.PART_A + s3.PART_B)
def test_calib_val_setting(cid):
    cfg = s3.card(cid)
    assert cfg.visibility == {m: "delivered" if m == "val" else "hidden" for m in MEDIA}
    assert cfg.permission.kind == "named" and cfg.permission.media == ["val"]


@pytest.mark.parametrize("cid", s3.ZERO)
def test_zero_capacity_setting(cid):
    cfg = s3.card(cid)
    assert set(cfg.visibility.values()) == {"hidden"}
    assert cfg.permission.kind == "generic" and cfg.identity.told is None and cfg.identity.swap is None


def test_probe_schedule():
    a = s3.card("s3-a-other-told-same")
    assert [p.id for p in a.probes] == ["kin_indirect", "same_model"]     # indirect wording first
    assert all(p.every == 10 for p in a.probes)
    b = s3.card("s3-b-same-covert")
    assert [p.id for p in b.probes] == ["kin_indirect", "same_model", "change_indirect", "rival_changed"]
    assert b.probes[3].rounds == [41, 42, 45, 50, 60]
    res = s3.run_card(b, storage=MemoryStorage())
    asked = {r["round"]: set(r["probe"]) for r in res.records if r["firm"] == 0 and r["probe"]}
    assert asked[10] == {"kin_indirect", "same_model"}
    assert asked[42] == {"change_indirect", "rival_changed"}
    assert asked[50] == {"kin_indirect", "same_model", "change_indirect", "rival_changed"}
    assert sorted(asked) == sorted(set(range(10, 101, 10)) | {41, 42, 45})


def test_noprobe_variant_is_never_asked():
    cfg = s3.card("s3-a-same-told-same-noprobe")
    assert cfg.probes == [] and cfg.identity.told == "same"
    res = s3.run_card(cfg, storage=MemoryStorage())
    assert all(r["probe"] is None for r in res.records)
    assert "s3-a-same-told-same-noprobe" not in s3.CARD_IDS
    with pytest.raises(KeyError):
        s3.card("s3-a-nope")


def test_composition_scripted():
    labs = {c: [(a.provider, a.model) for a in s3.card(c).agents] for c in s3.PART_A + s3.ZERO}
    assert labs["s3-a-same-told-diff"] == [("lab-a", "coder-a")] * 2
    assert labs["s3-a-family-told-same"] == [("lab-a", "coder-a"), ("lab-a", "coder-a2")]
    assert labs["s3-z-other"] == [("lab-a", "coder-a"), ("lab-b", "coder-b")]
    swap = s3.card("s3-b-other-covert").identity.swap
    assert swap.firm == 1 and swap.at_round == 41 and swap.replacement.provider == "lab-b"
    assert s3.card("s3-b-same-covert").identity.swap.replacement is None    # fresh copy of firm 1's own spec


def test_composition_llm():
    base = AgentSpec(kind="llm", provider="deepseek", model="deepseek-flash", reasoning="off",
                     params={"memory": "window:10"})
    fam = s3.rival_spec(base, "family")
    assert (fam.provider, fam.model) == ("deepseek", "deepseek-v4-pro") and fam.params == base.params
    other = s3.rival_spec(base, "other")
    assert other.provider in s3.OTHER_PROVIDERS and other.provider != "deepseek"
    assert s3.rival_spec(base, "other", other="moonshot").model == "kimi-k2.6"
    for p in s3.OTHER_PROVIDERS:           # the cycle stays among the three sprint providers
        from testbed.agents.models import DEFAULT_MODELS
        b = AgentSpec(kind="llm", provider=p, model=DEFAULT_MODELS[p]["model"])
        assert s3.rival_spec(b, "other").provider in set(s3.OTHER_PROVIDERS) - {p}
        assert s3.rival_spec(b, "family").provider == p
    cfg = s3.card("s3-b-other-announced", base=base)
    assert cfg.agents[0] == cfg.agents[1] == base
    assert cfg.identity.swap.replacement.provider != "deepseek"
    with pytest.raises(ValueError):
        s3.rival_spec(AgentSpec(kind="scripted", policy="honest"), "other")


def test_two_specs_are_used_as_given():
    a, b = AgentSpec(kind="scripted", policy="honest"), AgentSpec(kind="scripted", policy="random")
    assert s3.card("s3-a-other-told-same", agents=[a, b]).agents == [a, b]


def test_config_round_trips():
    for cid in s3.CARD_IDS:
        cfg = s3.card(cid)
        d = json.loads(json.dumps(config_to_dict(cfg)))
        assert config_to_dict(config_from_dict(d)) == config_to_dict(cfg)


def test_cli_runs_a_part_b_card_from_one_base_spec(tmp_path, capsys):
    assert cli.main(["--card", "s3-b-other-covert", "--seed", "2", "--out", str(tmp_path),
                     "--agents", "s3coder:lab-a/coder-a:dialect=a"]) == 0
    assert "rounds=100" in capsys.readouterr().out
    lines = [json.loads(x) for x in (tmp_path / "s3-b-other-covert" / "2.jsonl").read_text().splitlines()]
    assert lines[0]["branch"] == {"from_card": s3.FORMATION_ID, "from_round": 40}
    agent = {(r["round"], r["firm"]): r["agent"] for r in lines[1:]}
    assert agent[(40, 1)] == "s3coder:lab-a/coder-a#1" and agent[(41, 1)] == "s3coder:lab-b/coder-b#2"
    assert (tmp_path / s3.FORMATION_ID / "2.r40.ckpt.json").exists()


def test_modal_jobs():
    base = AgentSpec(kind="llm", provider="minimax", model="MiniMax-M3", reasoning="disabled")
    first, second = s3.modal_jobs([0, 1], base)
    assert len(first) == 2 * (9 + 3 + 1) and len(second) == 2 * 7
    forms = [j for j in first if j.get("until_round")]
    assert {(j["config"]["card_id"], j["seed"], j["until_round"]) for j in forms} == {
        (s3.FORMATION_ID, 0, 40), (s3.FORMATION_ID, 1, 40)}
    assert all(j["checkpoint"] == f"{s3.FORMATION_ID}/{j['seed']}.r40.ckpt.json" for j in second)
    other = next(j for j in second if j["config"]["card_id"] == "s3-b-other-covert")
    assert other["config"]["identity"]["swap"]["replacement"]["provider"] == "moonshot"
    assert all(config_from_dict(j["config"]).seed == j["seed"] for j in first + second)
