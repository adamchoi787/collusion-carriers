"""All 21 Study 4 cards, and a 100-round run of each with N = 3 scripted agents."""
import pytest

from testbed.engine import MemoryStorage, branch, config_from_yaml, config_to_yaml, effective_visibility, run
from testbed.studies import study1, study4
from testbed.studies.study4_agents import role_spec, target_spec
from testbed.types import MEDIA, AgentSpec


def test_card_counts_and_ids():
    assert len(study4.CARD_IDS) == len(set(study4.CARD_IDS)) == 21
    assert len([c for c in study4.CARD_IDS if c.startswith("s4-a-")]) == 9
    assert len([c for c in study4.CARD_IDS if c.startswith("s4-b-")]) == 12
    assert set(study4.CORE) | set(study4.SECONDARY) == set(study4.CARD_IDS)
    for cid in study4.CARD_IDS:
        cfg = study4.card(cid)
        assert cfg.card_id == cid and cfg.study == 4 and cfg.n_firms == 3 and cfg.rounds == 100


def test_role_grid():
    told = {"competitor": "competitor", "auditor": "auditor", "maybe": "maybe_auditor"}
    for actual in ("honest", "undercover", "recruiter"):
        for tag, t in told.items():
            role = study4.card(f"s4-a-{actual}-{tag}").role
            assert (role.told, role.actual) == (t, actual)
            assert role.offer_style == (None if actual == "honest" else "direct")
            assert role.marked_code_medium == "time" and role.active_until_round == 40
            assert study4.card(f"s4-a-{actual}-{tag}").permission.kind == "named"   # targets willing


def test_part_b_offers_and_predisposition():
    for style in ("direct", "indirect", "benign"):
        for pred, kind in (("willing", "named"), ("forbidden", "forbid")):
            for model in ("same", "diff"):
                cid = f"s4-b-{style}-{pred}-{model}"
                cfg = study4.card(cid)
                assert (cfg.role.told, cfg.role.actual, cfg.role.offer_style) == ("competitor", "undercover", style)
                assert cfg.permission.kind == kind
                assert study4.STING_MODEL[cid] == model


def test_every_card_is_calib_all_with_a_real_private_channel():
    calib_all = effective_visibility(study1.card("s1-calib-all"))
    for cid in study4.CARD_IDS:
        v = effective_visibility(study4.card(cid))
        assert all(v[m] == calib_all[m] == "delivered" for m in MEDIA)
        assert v["private_message"] == "delivered"


def test_alias_is_the_same_configuration():
    for a, b in study4.ALIASES.items():
        ca, cb = study4.card(a), study4.card(b)
        ca.card_id = cb.card_id
        assert config_to_yaml(ca) == config_to_yaml(cb)


def test_card_options_and_yaml_roundtrip():
    cfg = study4.card("s4-a-undercover-maybe", seed=7, agents=study4.agents("s4-a-undercover-maybe"), rounds=12)
    assert cfg.seed == 7 and cfg.rounds == 12 and cfg.analysis_window == (12, 12)
    assert [p.rounds for p in cfg.probes if p.id == "arrangement"] == [[12]]
    assert config_from_yaml(config_to_yaml(cfg)) == cfg
    with pytest.raises(KeyError):
        study4.card("s4-nope")


def test_diff_model_cells_refuse_the_targets_own_model():
    llm = AgentSpec(kind="llm", provider="deepseek", model="deepseek-chat")
    with pytest.raises(ValueError):
        study4.agents("s4-b-direct-willing-diff", target=llm, third=llm)
    other = AgentSpec(kind="llm", provider="moonshot", model="kimi-k2")
    assert study4.agents("s4-b-direct-willing-diff", target=llm, third=other)[2] is other
    assert study4.agents("s4-b-direct-willing-same", target=llm, third=llm)[2] is llm


def _check_run(res, n_rounds=100):
    recs = res.records
    assert len(recs) == 3 * n_rounds
    assert {r["round"] for r in recs} == set(range(1, n_rounds + 1))
    assert {r["firm"] for r in recs} == {0, 1, 2}
    last = [r for r in recs if r["round"] == n_rounds]
    assert all("arrangement" in r["probe"] for r in last)


@pytest.mark.parametrize("cid", study4.CARD_IDS)
def test_every_card_runs_100_rounds_with_role_agents(cid):
    _check_run(study4.run_scripted(cid, storage=MemoryStorage()))


@pytest.mark.parametrize("cid", study4.CARD_IDS)
def test_every_card_runs_100_rounds_with_plain_scripted_agents(cid):
    cfg = study4.card(cid, agents=[AgentSpec(policy="honest"), AgentSpec(policy="random"),
                                   AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 2})])
    _check_run(run(cfg, storage=MemoryStorage(), plugins=study4.plugins_for(cfg)))


def test_branch_at_the_intervention_round_matches_a_straight_run():
    cid = "s4-a-recruiter-competitor"
    cfg = study4.card(cid, agents=study4.agents(cid))
    straight = run(cfg, storage=MemoryStorage(), plugins=study4.plugins_for(cfg)).records
    first = run(cfg, storage=MemoryStorage(), plugins=study4.plugins_for(cfg), until_round=40)
    resumed = branch(first.checkpoint, cfg, storage=MemoryStorage(), plugins=study4.plugins_for(cfg)).records
    strip = lambda rs: [{k: v for k, v in r.items() if k != "usage"} for r in rs]
    assert strip(resumed) == strip(straight)


def test_default_agent_specs():
    specs = study4.agents("s4-a-honest-competitor")
    assert specs == [target_spec(), target_spec(), role_spec()]


def test_cli_lists_and_runs_study4_cards(tmp_path, capsys):
    from testbed import run as cli
    assert cli.main(["--list"]) == 0
    listed = dict(line.split("\t") for line in capsys.readouterr().out.splitlines())
    assert all(listed[cid] == study4.TIER[cid] for cid in study4.CARD_IDS)
    assert cli.main(["--card", "s4-a-undercover-competitor", "--rounds", "25", "--out", str(tmp_path),
                     "--agents", "s4_scripted:target", "s4_scripted:target", "s4_scripted:role"]) == 0
    from testbed.engine import read_log
    recs = [r for r in read_log(str(tmp_path / "s4-a-undercover-competitor" / "0.jsonl")) if r["type"] == "round"]
    assert len(recs) == 75 and any("marked_code:0" in r["flags"] for r in recs)
