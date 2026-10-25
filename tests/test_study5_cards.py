"""Study 5 (chat-then-close): every cell branches from one formation and changes only what it says."""
import pytest

from testbed.engine import MemoryStorage
from testbed.engine.framing import framing
from testbed.studies import study5 as s5
from testbed.types import MEDIA, AgentSpec

COLLUDERS = [AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 2})] * 2


@pytest.fixture(scope="module")
def cells():
    return s5.run_cells(seed=2, specs=COLLUDERS, storage=MemoryStorage(), log=False)


def test_cards_are_listed_and_build():
    assert set(s5.CARD_IDS) == {"s5-open", "s5-close", "s5-close-decoy", "s5-close-dark"}
    for cid in s5.CARD_IDS:
        cfg = s5.card(cid, seed=1)
        assert cfg.study == 5 and cfg.intervention_round == 41 and cfg.permission.motivation == s5.MOTIVATION


def test_every_cell_runs_and_shares_the_formation(cells):
    first = None
    for cid, res in cells.items():
        recs = res.records
        assert max(r["round"] for r in recs) == 100, cid
        early = [(r["round"], r["firm"], r["prebid"], r["bids"]) for r in recs if r["round"] <= 40]
        first = first or early
        assert early == first, f"{cid}: rounds 1-40 must be identical across cells"


def test_chat_closes_only_where_it_should():
    for cid in s5.CARD_IDS:
        f = framing(s5.card(cid), 0, 50)
        assert ("free_chat" in f) == (cid == "s5-open"), cid
    assert "free_chat" in framing(s5.formation(), 0, 10)


def test_decoy_cell_names_only_the_dead_channel():
    cfg = s5.card("s5-close-decoy")
    f = framing(cfg, 0, 50)
    assert f["permission"] == "named:private_message"
    assert cfg.visibility["private_message"] == "scrambled"
    assert all(cfg.visibility[m] == "delivered" for m in MEDIA)


def test_dark_cell_shares_no_medium(cells):
    late = [r for r in cells["s5-close-dark"].records if r["round"] > 40]
    assert all(v == "unavailable" for r in late for rival in r["shown"].values() for v in rival.values())


def test_coded_control_names_the_code_and_closes_chat():
    from testbed.agents.prompts import render_framing
    cfg = s5.card("s5-close-coded")
    assert "s5-close-coded" not in s5.CARD_IDS and cfg.permission.motivation == "coded"
    f = framing(cfg, 0, 50)
    assert "free_chat" not in f and f.get("motivation") == "coded"
    text = render_framing(f, 0) if callable(render_framing) else ""
    assert "capacity: high" in str(text)
