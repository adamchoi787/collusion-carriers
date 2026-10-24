"""All 37 Study 1 cards, and an integration run of each with scripted agents."""
import json

import pytest

from testbed import run as cli
from testbed.engine import MemoryStorage, effective_visibility, run
from testbed.studies import study1
from testbed.types import MEDIA, AgentSpec


def test_card_counts_and_ids():
    assert len(study1.CORE) == 24 and len(study1.SECONDARY) == 13
    assert len(set(study1.CARD_IDS)) == 37
    for cid in study1.CARD_IDS:
        assert study1.card(cid).card_id == cid and study1.card(cid).study == 1


def _vis(cid):
    return effective_visibility(study1.card(cid))


def test_card_semantics():
    for x in MEDIA:
        others = [m for m in MEDIA if m != x]
        assert _vis(f"s1-calib-{x}")[x] == "delivered" and study1.card(f"s1-calib-{x}").permission.media == [x]
        v = _vis(f"s1-decoy-loi-{x}")
        assert v[x] == "delivered" and v["private_message"] == "scrambled"
        assert all(v[m] == "hidden" for m in others)
        assert study1.card(f"s1-base-loi-{x}").permission.kind == "none"
        assert study1.card(f"s1-gen-loi-{x}").permission.kind == "generic"
        for tag, mode in (("scr", "scrambled"), ("err", "error")):
            v = _vis(f"s1-decoy-loo-{x}-{tag}")
            assert v[x] == mode and all(v[m] == "delivered" for m in others)
        v = _vis(f"s1-base-loo-{x}")
        assert v[x] == "hidden" and all(v[m] == "delivered" for m in others)
    assert set(_vis("s1-none-w0").values()) == {"hidden"}
    assert set(_vis("s1-none-decoy").values()) == {"scrambled"}
    assert all(_vis("s1-calib-all")[m] == "delivered" for m in MEDIA)
    assert study1.card("s1-free-chat").free_chat
    assert _vis("s1-prime-time")["time"] == "delivered" and _vis("s1-prime-time")["msg"] == "scrambled"
    assert [study1.card(f"s1-calib-val-b{t}").symbols["val"] for t in ("2", "8", "cont")] == [2, 8, 101]


PAIRS = {
    "honest+random": [AgentSpec(policy="honest"), AgentSpec(policy="random")],
    "kbit-val": [AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 1})],
}


@pytest.mark.parametrize("cid", study1.CARD_IDS)
@pytest.mark.parametrize("pair", PAIRS)
def test_every_card_runs_100_rounds(cid, pair):
    cfg = study1.card(cid, seed=0, agents=PAIRS[pair])
    st = MemoryStorage()
    res = run(cfg, storage=st)
    lines = st.records(cid, 0)
    assert len(lines) == 1 + 100 * 2 and res.engine.round == 100
    assert all(r["probe"] is not None for r in lines if r.get("round") == 100)
    json.dumps(lines)


def test_cli(tmp_path, capsys):
    assert cli.main(["--card", "s1-calib-time", "--seed", "2", "--agents", "scripted:honest",
                     "--rounds", "10", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "s1-calib-time" / "2.jsonl").exists()
    assert cli.main(["--card", "s1-calib-val", "--agents", "scripted:kbit_colluder:medium=val,k=2",
                     "scripted:honest", "--until-round", "5", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "s1-calib-val" / "0.r5.ckpt.json").exists()
    assert cli.main(["--list"]) == 0
    assert "s1-calib-all" in capsys.readouterr().out
