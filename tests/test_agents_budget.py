"""The spend guard: zero provider caps block, per-provider and optional total caps hold, and
concurrent reservations never overshoot (threads, separate ledger handles,
and the modal.Dict backend with an in-memory fake)."""
import threading
import time

import pytest

from testbed.agents.budget import (BudgetExceeded, CappedLedger, Caps, LocalLedger, ModalLedger, Prices,
                                   UnknownPrice)


def caps(total=1.0, **per):
    return Caps(total=total, per_provider=per)


def test_zero_or_missing_cap_blocks(tmp_path, monkeypatch):
    for k in ("BUDGET_USD_TOTAL", "BUDGET_USD_OPENAI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("testbed.agents.budget.load_env", lambda: None)
    c = Caps.from_env()
    assert c.total is None and c.for_provider("openai") == 0
    led = LocalLedger(tmp_path / "l.jsonl", caps=c)
    with pytest.raises(BudgetExceeded):
        led.reserve("openai", 0.0)
    led = LocalLedger(tmp_path / "l2.jsonl", caps=caps(10.0, openai=0.0, anthropic=1.0))
    with pytest.raises(BudgetExceeded):
        led.reserve("openai", 0.001)
    led.reserve("anthropic", 0.001)


def test_bad_cap_values_parse_to_zero(tmp_path, monkeypatch):
    monkeypatch.setattr("testbed.agents.budget.load_env", lambda: None)
    monkeypatch.setenv("BUDGET_USD_TOTAL", "lots")
    monkeypatch.setenv("BUDGET_USD_DEEPSEEK", "-3")
    c = Caps.from_env()
    assert c.total == 0 and c.for_provider("deepseek") == 0
    led = LocalLedger(tmp_path / "l.jsonl", caps=Caps(total=c.total, per_provider={"deepseek": 1.0}))
    with pytest.raises(BudgetExceeded, match="BUDGET_USD_TOTAL"):
        led.reserve("deepseek", 0.01)  # a set-but-invalid total fails closed


def test_unset_or_empty_total_means_no_overall_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("testbed.agents.budget.load_env", lambda: None)
    for raw in (None, "", "  "):
        if raw is None:
            monkeypatch.delenv("BUDGET_USD_TOTAL", raising=False)
        else:
            monkeypatch.setenv("BUDGET_USD_TOTAL", raw)
        assert Caps.from_env().total is None
    led = LocalLedger(tmp_path / "l.jsonl", caps=Caps(total=None, per_provider={"a": 3.0, "b": 3.0}))
    led.reserve("a", 2.5)
    led.reserve("b", 2.5)          # 5.0 in total: no overall cap applies
    with pytest.raises(BudgetExceeded, match="b:"):
        led.reserve("b", 0.6)      # the provider cap still does
    with pytest.raises(BudgetExceeded, match="c:"):
        led.reserve("c", 0.01)     # no cap for c -> blocked


def test_spend_report_shows_no_total_cap():
    from testbed.agents.spend import report
    from testbed.agents.budget import _empty_state

    assert "no overall cap" in report(_empty_state(), Caps(total=None, per_provider={"openai": 1.0}))
    assert "no overall cap" not in report(_empty_state(), Caps(total=5.0))


def test_per_provider_and_total_caps(tmp_path):
    led = LocalLedger(tmp_path / "l.jsonl", caps=caps(1.0, a=0.6, b=0.6))
    t = led.reserve("a", 0.5)
    with pytest.raises(BudgetExceeded, match="a:"):
        led.reserve("a", 0.2)
    led.reserve("b", 0.4)
    with pytest.raises(BudgetExceeded, match="total"):
        led.reserve("b", 0.15)
    led.settle(t, 0.1, {"input": 10, "output": 2})
    led.reserve("b", 0.15)  # reservation freed down to the actual cost
    s = led.summary()["providers"]["a"]
    assert s["settled_usd"] == pytest.approx(0.1) and s["calls"] == 1 and s["input"] == 10


def test_release_frees_reservation(tmp_path):
    led = LocalLedger(tmp_path / "l.jsonl", caps=caps(1.0, a=1.0))
    t = led.reserve("a", 0.9)
    led.release(t)
    led.reserve("a", 0.9)


def test_ledger_survives_reopen(tmp_path):
    path = tmp_path / "l.jsonl"
    led = LocalLedger(path, caps=caps(1.0, a=1.0))
    led.settle(led.reserve("a", 0.5), 0.4)
    again = LocalLedger(path, caps=caps(1.0, a=1.0))
    with pytest.raises(BudgetExceeded):
        again.reserve("a", 0.7)


def _hammer(make_ledger, n_threads=12, est=0.3):
    wins, lock = [], threading.Lock()
    barrier = threading.Barrier(n_threads)

    def worker():
        led = make_ledger()
        barrier.wait()
        try:
            t = led.reserve("a", est)
        except BudgetExceeded:
            return
        with lock:
            wins.append(t)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return wins


def test_concurrent_reservations_never_overshoot_shared_handle(tmp_path):
    led = LocalLedger(tmp_path / "l.jsonl", caps=caps(1.0, a=1.0))
    wins = _hammer(lambda: led)
    assert len(wins) == 3  # 3 x 0.3 <= 1.0 < 4 x 0.3


def test_concurrent_reservations_never_overshoot_separate_handles(tmp_path):
    # Each thread opens its own ledger, as separate processes would: only the
    # file lock serialises them.
    path = tmp_path / "l.jsonl"
    wins = _hammer(lambda: LocalLedger(path, caps=caps(1.0, a=1.0)))
    assert len(wins) == 3
    reserved = LocalLedger(path, caps=caps()).summary()["providers"]["a"]["reserved"]
    assert sum(r["usd"] for r in reserved.values()) <= 1.0


class FakeModalDict:
    """modal.Dict's get/put(skip_if_exists)/pop semantics, with a small delay
    inside each call to widen race windows."""

    def __init__(self):
        self.d, self.lock = {}, threading.Lock()

    def get(self, k, default=None):
        time.sleep(0.0005)
        with self.lock:
            return self.d.get(k, default)

    def put(self, k, v, *, skip_if_exists=False):
        time.sleep(0.0005)
        with self.lock:
            if skip_if_exists and k in self.d:
                return False
            self.d[k] = v
            return True

    def pop(self, k):
        with self.lock:
            return self.d.pop(k)


def test_modal_backend_concurrent_containers_never_overshoot():
    store = FakeModalDict()
    wins = _hammer(lambda: ModalLedger(store, caps=caps(1.0, a=1.0)), n_threads=10)
    assert len(wins) == 3
    led = ModalLedger(store, caps=caps(1.0, a=1.0))
    for t in wins:
        led.settle(t, 0.05, {"output": 1})
    s = led.summary()["providers"]["a"]
    assert s["settled_usd"] == pytest.approx(0.15) and s["reserved"] == {}
    assert "lock" not in store.d


def test_modal_backend_breaks_stale_lock():
    store = FakeModalDict()
    store.d["lock"] = {"owner": "dead", "ts": time.time() - 3600}
    led = ModalLedger(store, caps=caps(1.0, a=1.0))
    led.reserve("a", 0.1)


def test_capped_ledger_adds_a_run_cap(tmp_path):
    inner = LocalLedger(tmp_path / "l.jsonl", caps=caps(10.0, a=10.0))
    led = CappedLedger(inner, 0.5)
    t = led.reserve("a", 0.4)
    with pytest.raises(BudgetExceeded, match="run cap"):
        led.reserve("a", 0.2)
    led.settle(t, 0.1)
    led.reserve("a", 0.35)
    assert inner.summary()["providers"]["a"]["settled_usd"] == pytest.approx(0.1)


def test_release_stale(tmp_path):
    led = LocalLedger(tmp_path / "l.jsonl", caps=caps(1.0, a=1.0))
    led.reserve("a", 0.9)
    assert led.release_stale(older_than_s=3600) == 0
    assert led.release_stale(older_than_s=-1) == 1
    led.reserve("a", 0.9)


def test_prices_estimate_and_cost():
    p = Prices.load()
    est = p.estimate("anthropic", "claude-haiku-5-5", 10_000, 1_000)
    assert est == pytest.approx((10_000 * 0.10 + 1_000 * 0.50) / 1e6)
    # cached tokens at the cached price; unknown cached price falls back to input
    c = p.cost("openai", "gpt-6-luna", {"input": 1_000_000, "cached": 500_000, "output": 0})
    assert c == pytest.approx(0.5 * 0.10 + 0.5 * 0.01)
    c = p.cost("deepseek", "deepseek-v4-pro", {"input": 1_000_000, "cached": 1_000_000, "output": 0})
    assert c == pytest.approx(1.32)
    with pytest.raises(UnknownPrice):
        p.estimate("openai", "gpt-unknown", 1, 1)


def test_every_price_row_is_marked_for_verification():
    t = Prices.load().table
    for prov, row in t["providers"].items():
        for model, r in row["models"].items():
            assert r["verify"] is True and r["source"].startswith("https://"), (prov, model)
            assert r["input"] > 0 and r["output"] > 0
