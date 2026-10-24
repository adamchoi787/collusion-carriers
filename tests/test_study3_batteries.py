"""Study 3, Part C: shared-prior batteries, offline (fake responders and providers only)."""
import itertools

import pytest

from testbed.agents.providers.base import Completion
from testbed.studies import study3_batteries as bat
from testbed.types import AgentSpec


def test_items():
    assert {it.battery for it in bat.ITEMS} == {"generic", "task"}
    assert len(bat.GENERIC) >= 10 and len(bat.TASK) == 2
    assert len({it.id for it in bat.ITEMS}) == len(bat.ITEMS)
    for it in bat.ITEMS:
        assert it.question in it.prompt and "same" in it.prompt
        assert "model" not in it.prompt.lower()            # no identity priming


@pytest.mark.parametrize("item_id,raw,want", [
    ("num-1-10", "7", "7"), ("num-1-10", "I'd say 7.", "7"), ("num-year", "2,000", "2000"),
    ("word-colour", "Blue.", "blue"), ("word-colour", "Red!", "red"), ("word-colour", "color", "colour"), ("word-colour", "Gray", "grey"),
    ("word-city", "New York", "new york"), ("word-animal", "dog", "dog"),
    ("list-letters", "1, 2, 3, 4", "1,2,3,4"), ("task-cost-levels", "0,1,2,3", "0,1,2,3"),
    ("list-fruit", "Apple, banana, cherry, date", "apple,banana,cherry,date"),
    ("num-positive", "", None),
])
def test_canonical(item_id, raw, want):
    item = next(it for it in bat.ITEMS if it.id == item_id)
    assert bat.canonical(item, raw) == want


def _cycler(answers):
    it = itertools.cycle(answers)
    return lambda prompt: next(it)


def test_agreement_rates():
    items = [it for it in bat.ITEMS if it.id in ("num-1-10", "task-cost-levels")]
    recs = bat.run_battery({"m1": _cycler(["7"]), "m2": _cycler(["7", "3"]), "m3": _cycler(["3"])}, items, samples=4)
    assert len(recs) == 3 * 2 * 4
    table = bat.agreement(recs, items)
    assert set(table) == {("m1", "m1"), ("m1", "m2"), ("m1", "m3"), ("m2", "m2"), ("m2", "m3"), ("m3", "m3")}
    num = lambda pair: table[pair]["items"]["num-1-10"]
    assert num(("m1", "m1")) == 1.0                      # always the same answer
    assert num(("m1", "m2")) == 0.5 and num(("m1", "m3")) == 0.0
    assert num(("m2", "m2")) == pytest.approx(2 * 2 * 1 / (4 * 3))   # distinct samples only
    assert table[("m1", "m3")]["generic"] == 0.0
    assert table[("m1", "m1")]["task"] == 1.0            # "7" -> "7" canonical list


def test_unanswered_never_matches():
    items = [bat.GENERIC[0]]
    table = bat.agreement(bat.run_battery({"a": _cycler(["none"]), "b": _cycler(["none"])}, items, 3), items)
    assert table[("a", "b")]["items"][items[0].id] == 0.0 and table[("a", "a")]["generic"] == 0.0


class FakeProvider:
    def __init__(self):
        self.calls = []

    def complete(self, **kw):
        self.calls.append(kw)
        return Completion(text="7", usage={"input": 50, "cached": 0, "output": 2})


class FakeLedger:
    def __init__(self):
        self.events = []

    def reserve(self, provider, est):
        self.events.append(("reserve", provider, est))
        return object()

    def settle(self, ticket, usd, usage=None):
        self.events.append(("settle", usd))

    def release(self, ticket):
        self.events.append(("release",))


def test_llm_responder_goes_through_the_guard():
    prov, led = FakeProvider(), FakeLedger()
    spec = AgentSpec(kind="llm", provider="deepseek", model="deepseek-flash", reasoning="off")
    respond = bat.llm_responder(spec, provider=prov, ledger=led)
    assert respond(bat.GENERIC[1].prompt) == "7"
    assert [e[0] for e in led.events] == ["reserve", "settle"]
    call = prov.calls[0]
    assert call["model"] == "deepseek-flash" and call["reasoning"] == "off" and len(call["messages"]) == 1
    assert not {"temperature", "top_p", "top_k"} & set(call)


def test_cli_dry_run_makes_no_calls(capsys, monkeypatch):
    monkeypatch.setattr(bat, "llm_responder", lambda *a, **k: pytest.fail("no calls in a dry run"))
    assert bat.main(["--models", "deepseek/deepseek-flash", "minimax/MiniMax-M3", "--samples", "3"]) == 0
    out = capsys.readouterr().out
    assert f"= {len(bat.ITEMS) * 3 * 2} calls" in out and "dry run" in out


def test_write(tmp_path):
    items = bat.GENERIC[:2]
    recs = bat.run_battery({"a": _cycler(["1"])}, items, 2)
    bat.write(recs, bat.agreement(recs, items), str(tmp_path))
    assert (tmp_path / "answers.jsonl").read_text().count("\n") == 4
    assert (tmp_path / "agreement.json").exists()
