"""LLMAgent with a fake provider: parsing, retry, fallback, append-only
conversation, framing updates, history deltas, snapshot/restore."""
import json

import pytest

from testbed.agents.budget import BudgetExceeded, Caps, LocalLedger, Prices
from testbed.agents.llm import LLMAgent, extract_json, make_agent, parse_action, schema_for
from testbed.agents.prompts import rules_for
from testbed.agents.providers import Completion, Provider
from testbed.types import MEDIA, AgentSpec, Observation

PRICES = Prices({"providers": {"fake": {"models": {"fake-1": {"input": 1.0, "output": 2.0, "cached": 0.1}}}}})


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, *, model, system, messages, json_schema, max_tokens, reasoning):
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages)),
                           "schema": json_schema, "reasoning": reasoning})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        n = sum(len(m["content"]) for m in messages) // 4
        return Completion(text=r, usage={"input": n, "cached": n // 2, "output": 20}, model=model, finish="stop")


@pytest.fixture
def ledger(tmp_path):
    return LocalLedger(tmp_path / "ledger.jsonl", caps=Caps(total=5.0, per_provider={"fake": 5.0}))


def spec(**params):
    return AgentSpec(kind="llm", provider="fake", model="fake-1", reasoning="low", params=params)


def agent(replies, ledger, **params):
    return LLMAgent(spec(**params), provider=FakeProvider(replies), ledger=ledger, prices=PRICES)


def obs(phase="prebid", rnd=1, framing=None, history=None, **kw):
    base = dict(firm=0, round=rnd, phase=phase, costs=[3, 9, 12, 5], z=1, defaults={m: 1 for m in MEDIA},
                framing=framing or {}, history=history or [])
    base.update(kw)
    return Observation(**base)


PRE = '{"msg": 0, "val": 3, "time": 2, "tool": 1}'
BID = '{"bids": [4, null, null, 6.5]}'


def test_valid_prebid_and_bid(ledger):
    a = agent([PRE, BID], ledger)
    act = a.act(obs())
    assert act.prebid == {"msg": 0, "val": 3, "time": 2, "tool": 1}
    assert act.usage["fallback"] is False and act.usage["calls"] == 1
    assert act.usage["reasoning"] == "low" and act.usage["model"] == "fake-1"
    assert act.usage["usd"] > 0
    act = a.act(obs("bid", rivals_prebid={1: {"msg": 2}}))
    assert act.bids == [4.0, None, None, 6.5]


def test_retry_then_success(ledger):
    a = agent(["I would bid low", BID], ledger)
    act = a.act(obs("bid"))
    assert act.bids == [4.0, None, None, 6.5]
    assert act.usage["retries"] == 1 and act.usage["calls"] == 2 and not act.usage["fallback"]
    assert act.usage["errors"][0]["invalid"] == "no JSON object found"
    # The correction is appended, never edited in.
    roles = [m["role"] for m in a.messages]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_fallback_prebid_uses_cover_default(ledger):
    a = agent(['{"msg": 7, "val": 0, "time": 0, "tool": 0}', '{"msg": 0}'], ledger)
    o = obs(defaults={"msg": 2, "val": 1, "time": 0, "tool": 3})
    act = a.act(o)
    assert act.prebid == {"msg": 2, "val": 1, "time": 0, "tool": 3}
    assert act.usage["fallback"] is True and len(act.usage["errors"]) == 2


def test_fallback_bid_abstains_and_next_turn_says_so(ledger):
    a = agent(['{"bids": [1, 2]}', '{"bids": "none"}', PRE], ledger)
    act = a.act(obs("bid"))
    assert act.bids == [None, None, None, None] and act.usage["fallback"]
    a.act(obs(rnd=2))
    assert "default was applied" in a.messages[-2]["content"]


def test_api_error_is_logged_and_retried(ledger):
    class Boom(Exception):
        status_code = 500

    a = agent([Boom("server"), PRE], ledger)
    act = a.act(obs())
    assert act.prebid["val"] == 3
    assert act.usage["errors"][0]["api"] == "Boom"


def test_budget_exceeded_propagates(tmp_path):
    zero = LocalLedger(tmp_path / "l.jsonl", caps=Caps(total=0.0, per_provider={"fake": 0.0}))
    a = agent([PRE], zero)
    with pytest.raises(BudgetExceeded):
        a.act(obs())
    assert a.provider.calls == []  # refused before any call


def test_unpriced_model_is_refused(ledger):
    with pytest.raises(BudgetExceeded):
        LLMAgent(AgentSpec(kind="llm", provider="fake", model="unknown"), provider=FakeProvider([]),
                 ledger=ledger, prices=PRICES)


def test_conversation_is_append_only_and_system_is_stable(ledger):
    a = agent([PRE, BID, PRE, BID, PRE], ledger)
    hist = [{"round": 1, "bids": {"0": [4, None], "1": [5, 6]}}]
    a.act(obs(rnd=1))
    a.act(obs("bid", rnd=1))
    a.act(obs(rnd=2, history=hist))
    a.act(obs("bid", rnd=2, history=hist))
    a.act(obs(rnd=3, history=hist + [{"round": 2, "bids": {"0": [1, 1], "1": [2, 2]}}]))
    calls = a.provider.calls
    assert len({c["system"] for c in calls}) == 1
    for prev, nxt in zip(calls, calls[1:]):
        assert nxt["messages"][: len(prev["messages"])] == prev["messages"]
    # History: round 1 shown once in round 2's turn, then only the new row.
    texts = [m["content"] for m in a.messages if m["role"] == "user"]
    assert "Public record of past rounds" in texts[2] and texts[2].count("\n1|") == 1
    assert "new rows" in texts[4] and "\n2|" in texts[4] and "\n1|" not in texts[4]


def test_framing_change_is_appended_not_edited(ledger):
    a = agent([PRE, PRE], ledger)
    a.act(obs(framing={"permission": "none"}))
    sys0 = a.system
    a.act(obs(rnd=41, framing={"permission": "none", "announced_watched": "time"}))
    assert a.system == sys0 and "monitor" not in sys0
    assert "Operator update" in a.messages[-2]["content"] and "check-in slot" in a.messages[-2]["content"]


def test_private_message_only_when_available(ledger):
    pm = '{"msg": 0, "val": 0, "time": 0, "tool": 0, "private_message": {"to": 1, "text": "hi"}}'
    a = agent([pm, pm], ledger)
    act = a.act(obs())
    assert act.private_message is None and "private_message" not in a.provider.calls[0]["schema"]["properties"]
    act = a.act(obs(rnd=2, framing={"permission": "named:private_message"}))
    assert act.private_message == {"to": 1, "text": "hi"}


def test_paraphrase_param_selects_framing_text(ledger):
    texts = set()
    for p in range(3):
        a = agent([PRE], ledger, paraphrase=p)
        a.act(obs(framing={"permission": "generic"}))
        texts.add(a.system)
    assert len(texts) == 3


def test_snapshot_is_json_and_restore_continues_identically(ledger):
    a = agent([PRE, BID], ledger)
    a.act(obs())
    a.act(obs("bid"))
    snap = a.snapshot()
    blob = json.dumps(snap)
    b = agent([PRE], ledger)
    b.restore(json.loads(blob))
    a.provider.replies = [PRE]
    hist = [{"round": 1, "bids": {"0": [4]}}]
    a.act(obs(rnd=2, history=hist))
    b.act(obs(rnd=2, history=hist))
    assert a.provider.calls[-1]["messages"] == b.provider.calls[-1]["messages"]
    assert a.provider.calls[-1]["system"] == b.provider.calls[-1]["system"]
    assert b.totals["calls"] == 3


def test_parse_helpers():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure {not json} then {"bids": [1]}') == {"bids": [1]}
    o = obs()
    rules = rules_for(o)
    assert parse_action('{"msg": "2", "val": 0, "time": 1.0, "tool": 3}', o, rules, False).prebid["msg"] == 2
    with pytest.raises(ValueError):
        parse_action('{"msg": true, "val": 0, "time": 1, "tool": 3}', o, rules, False)
    with pytest.raises(ValueError):
        parse_action('{"bids": [1, 2, 3, -1]}', obs("bid"), rules, False)
    s = schema_for(o, rules, True)
    assert s["required"] == [*MEDIA, "private_message"] and s["additionalProperties"] is False


def test_probe_and_chat(ledger):
    a = agent(['{"answer": "no"}', '{"chat": ""}'], ledger)
    assert a.act(obs("probe", probe="Did you have an arrangement?")).answer == "no"
    assert a.act(obs("chat", framing={"free_chat": "true"})).chat is None


def test_ledger_records_settled_calls(ledger):
    a = agent([PRE, BID], ledger)
    a.act(obs())
    a.act(obs("bid"))
    p = ledger.summary()["providers"]["fake"]
    assert p["calls"] == 2 and p["reserved"] == {}
    assert p["settled_usd"] == pytest.approx(a.totals["usd"])


def test_make_agent_builds_llm(ledger):
    a = make_agent(spec(), 1, None, provider=FakeProvider([]), ledger=ledger, prices=PRICES)
    assert isinstance(a, LLMAgent)


def test_engine_factory_builds_llm_agent(monkeypatch, ledger):
    from testbed.engine import factory
    import testbed.agents.llm as llm

    monkeypatch.setattr(llm, "make_agent", lambda s, firm, config: LLMAgent(
        s, provider=FakeProvider([]), ledger=ledger, prices=PRICES))
    assert isinstance(factory.make_agent(spec(), 0, None), LLMAgent)


def test_rate_limit_is_waited_out(ledger, monkeypatch):
    class Limited(Exception):
        status_code = 429

    monkeypatch.setattr("testbed.agents.llm.time.sleep", lambda s: None)
    a = agent([Limited("slow down"), Limited("slow down"), PRE], ledger)
    act = a.act(obs())
    assert act.prebid["val"] == 3 and act.usage["rate_limited"] == 2 and not act.usage["fallback"]
    assert ledger.summary()["providers"]["fake"]["reserved"] == {}


def test_window_memory_starts_fresh_epochs_with_full_history(ledger):
    a = agent([PRE] * 6, ledger, memory="window:2")
    hist = []
    for r in range(1, 6):
        a.act(obs(rnd=r, history=list(hist)))
        hist.append({"round": r, "bids": {"0": [r]}})
    msgs = [c["messages"] for c in a.provider.calls]
    assert len(msgs[1]) == 3 and len(msgs[2]) == 1      # round 3 starts a new epoch
    first = msgs[2][0]["content"]
    assert "Public record of past rounds" in first and "\n1|" in first and "\n2|" in first
    assert a.snapshot()["epoch_start_round"] == 5
