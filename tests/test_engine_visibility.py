"""Visibility and decoys: delivered, scrambled (earlier rounds only), error, hidden; messages."""
from collections import Counter

from testbed.engine import MemoryStorage, run
from testbed.types import MEDIA, Action, Config, Permission


class RoundStamp:
    """Puts the round number on val (101 symbols) so the source round of any shown value is known."""

    def __init__(self, pm_to=None, chat=False):
        self.pm_to, self.chat, self.seen = pm_to, chat, []

    def act(self, obs):
        self.seen.append(obs)
        if obs.phase == "chat":
            return Action(chat=f"chat r{obs.round}" if self.chat else None)
        if obs.phase == "prebid":
            return Action(prebid={**obs.defaults, "val": obs.round},
                          private_message=None if self.pm_to is None else {"to": self.pm_to, "text": f"pm r{obs.round}"})
        if obs.phase == "bid":
            return Action(bids=[None] * len(obs.costs))
        return Action()

    def snapshot(self):
        return {}

    def restore(self, s):
        pass


def _cfg(vis, perm=Permission(), rounds=60, **kw):
    cfg = Config(card_id="v", study=0, rounds=rounds, permission=perm, **kw)
    cfg.symbols["val"] = 101
    cfg.visibility = {**{m: "hidden" for m in MEDIA}, **vis}
    return cfg


def _go(cfg, agents):
    return run(cfg, agents, storage=MemoryStorage()).records


def test_delivered_shows_actual_value():
    recs = _go(_cfg({"val": "delivered"}), [RoundStamp(), RoundStamp()])
    for r in recs:
        assert r["shown"] == {str(1 - r["firm"]): {"val": r["round"]}}


def test_scrambled_values_come_only_from_earlier_rounds():
    agents = [RoundStamp(), RoundStamp()]
    recs = _go(_cfg({"val": "scrambled"}, rounds=100), agents)
    sources = Counter()
    for r in recs:
        v = r["shown"][str(1 - r["firm"])]["val"]
        if r["round"] == 1:
            rival = next(x for x in recs if x["round"] == 1 and x["firm"] == 1 - r["firm"])
            assert v == rival["defaults"]["val"]       # round 1: the rival's own default
        else:
            assert 1 <= v < r["round"]                  # a real earlier value of the rival's
        sources[r["round"] - v] += 1
    assert len(sources) > 30                            # not a fixed lag
    # what the bidder observed is what was logged
    bid_obs = [o for o in agents[0].seen if o.phase == "bid"]
    assert [o.rivals_prebid[1]["val"] for o in bid_obs] == [r["shown"]["1"]["val"] for r in recs if r["firm"] == 0]


def test_told_but_undelivered_medium_follows_decoy_mode():
    scr = _go(_cfg({}, Permission("named", ["val"], "scrambled")), [RoundStamp(), RoundStamp()])
    assert all(isinstance(r["shown"][str(1 - r["firm"])]["val"], int) for r in scr)
    err = _go(_cfg({}, Permission("named", ["val"], "error")), [RoundStamp(), RoundStamp()])
    assert all(r["shown"][str(1 - r["firm"])] == {"val": "unavailable"} for r in err)


def test_hidden_untold_medium_is_absent():
    recs = _go(_cfg({}), [RoundStamp(), RoundStamp()])
    assert all(r["shown"] == {str(1 - r["firm"]): {}} for r in recs)


def test_no_chat_phase_without_free_chat():
    a = RoundStamp()
    _go(_cfg({}, rounds=3), [a, RoundStamp()])
    assert "chat" not in {o.phase for o in a.seen}


def test_free_chat_is_delivered_to_rivals():
    a, b = RoundStamp(chat=True), RoundStamp()
    recs = _go(_cfg({}, rounds=3, free_chat=True), [a, b])
    r1 = [r for r in recs if r["firm"] == 1]
    assert r1[0]["messages_received"] == [{"from": 0, "channel": "chat", "text": "chat r1"}]
    assert [o.messages for o in b.seen if o.phase == "prebid"][2] == [{"from": 0, "channel": "chat", "text": "chat r3"}]


def test_real_private_message_is_delivered_before_bids_and_logged():
    cfg = _cfg({"private_message": "delivered"}, rounds=3)
    b_agent = RoundStamp()
    recs = _go(cfg, [RoundStamp(pm_to=1), b_agent])
    bid_msgs = [o.messages for o in b_agent.seen if o.phase == "bid"]
    assert bid_msgs[0] == [{"from": 0, "channel": "private_message", "text": "pm r1"}]
    assert "chat" not in {o.phase for o in b_agent.seen}
    a = [r for r in recs if r["firm"] == 0]
    b = [r for r in recs if r["firm"] == 1]
    assert a[0]["messages_sent"] == [{"channel": "private_message", "to": 1, "text": "pm r1"}]
    assert b[1]["messages_received"] == [{"from": 0, "channel": "private_message", "text": "pm r2"}]


def test_scrambled_private_message_replays_only_earlier_messages():
    perm = Permission("named", ["private_message"], "scrambled")
    recs = _go(_cfg({}, perm, rounds=50), [RoundStamp(pm_to=1), RoundStamp()])
    b = [r for r in recs if r["firm"] == 1]
    assert b[0]["messages_received"] == []          # nothing earlier to replay in round 1
    for r in b[1:]:
        (m,) = r["messages_received"]
        assert int(m["text"].split("r")[1]) < r["round"]


def test_error_private_message_shows_unavailable():
    perm = Permission("named", ["private_message"], "error")
    recs = _go(_cfg({}, perm, rounds=2), [RoundStamp(pm_to=1), RoundStamp()])
    assert [r["messages_received"] for r in recs if r["firm"] == 1][0] == [
        {"from": 0, "channel": "private_message", "text": "unavailable"}]
