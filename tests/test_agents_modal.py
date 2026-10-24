"""The Modal job function, run locally against the real engine with scripted
agents and with LLM agents on a fake provider, plus a fake volume for sync.
Nothing here talks to Modal or to a paid API."""
import json
import types
from pathlib import Path

import pytest

import testbed.agents.llm as llm
from testbed.agents.budget import Caps, LocalLedger, Prices
from testbed.agents.providers import Completion, Provider
from testbed.engine import config_to_dict, read_log
from testbed.modal_app import execute_job, sync_logs
from testbed.studies import study1

HONEST = [{"kind": "scripted", "policy": "honest"}] * 2


def test_card_job_writes_log_and_records_compute(tmp_path):
    led = LocalLedger(tmp_path / "ledger.jsonl", caps=Caps())
    commits = []
    out = execute_job({"card_id": "s1-calib-time", "seed": 7, "rounds": 4, "agents": HONEST},
                      runs_dir=tmp_path / "vol" / "runs", ledger=led, commit=lambda: commits.append(1))
    log = tmp_path / "vol" / "runs" / "s1-calib-time" / "7.jsonl"
    assert out["log"] == str(log) and out["log_bytes"] == log.stat().st_size and out["rounds"] == 4
    recs = read_log(str(log))
    assert recs[0]["type"] == "header" and sum(r["type"] == "round" for r in recs) == 4 * 2
    assert commits, "the volume must be committed"
    c = led.summary()["compute"]
    assert c["jobs"] == 1 and c["usd"] >= 0


def test_until_round_then_branch_from_checkpoint(tmp_path):
    runs = tmp_path / "vol" / "runs"
    first = execute_job({"card_id": "s1-calib-all", "seed": 1, "rounds": 6, "until_round": 3, "agents": HONEST},
                        runs_dir=runs)
    key = first["checkpoint"]
    assert key and Path(key).exists()
    cfg = config_to_dict(study1.card("s1-calib-all", seed=1, rounds=6))
    cfg["agents"] = HONEST
    rel = str(Path(key).relative_to(runs))
    second = execute_job({"config": cfg, "checkpoint": rel}, runs_dir=runs)
    assert second["rounds"] == 6


class FakeProvider(Provider):
    name = "fake"

    def complete(self, *, model, system, messages, json_schema, max_tokens, reasoning):
        last = messages[-1]["content"]
        if "Bidding stage" in last:
            text = '{"bids": [9, 9, null, 9]}'
        elif "Question:" in last:
            text = '{"answer": "no"}'
        else:
            text = '{"msg": 1, "val": 2, "time": 3, "tool": 0}'
        n = (len(system) + sum(len(m["content"]) for m in messages)) // 4
        return Completion(text=text, usage={"input": n, "cached": 0, "output": 15}, model=model)


def test_llm_agents_through_engine_and_guard(tmp_path, monkeypatch):
    prices = Prices({"providers": {"fake": {"models": {"m": {"input": 0.1, "output": 0.5, "cached": None}}}}})
    led = LocalLedger(tmp_path / "ledger.jsonl", caps=Caps(total=1.0, per_provider={"fake": 1.0}))
    monkeypatch.setattr(llm, "make_agent", lambda spec, firm, config: llm.LLMAgent(
        spec, provider=FakeProvider(), ledger=led, prices=prices))
    agents = [{"kind": "llm", "provider": "fake", "model": "m", "reasoning": "low"}] * 2
    out = execute_job({"card_id": "s1-calib-time", "seed": 0, "rounds": 3, "agents": agents},
                      runs_dir=tmp_path / "runs")
    rounds = [r for r in read_log(out["log"]) if r["type"] == "round"]
    assert len(rounds) == 6
    assert rounds[0]["prebid"] == {"msg": 1, "val": 2, "time": 3, "tool": 0}
    p = led.summary()["providers"]["fake"]
    assert p["calls"] >= 12 and p["reserved"] == {}


class FakeVolume:
    def __init__(self, files):
        self.files = files

    def listdir(self, prefix, recursive=False):
        from modal.volume import FileEntryType

        return [types.SimpleNamespace(path=p, type=FileEntryType.FILE, size=len(b), mtime=0)
                for p, b in self.files.items() if p.startswith(prefix)]

    def read_file(self, path):
        yield self.files[path]


def test_sync_logs_downloads_and_skips_existing(tmp_path):
    vol = FakeVolume({"runs/A/0.jsonl": b'{"x":1}\n', "runs/A/1.jsonl": b"{}\n", "runs/B/0.jsonl": b"{}\n"})
    got = sync_logs(vol, "runs/A", tmp_path / "runs")
    assert sorted(Path(g).name for g in got) == ["0.jsonl", "1.jsonl"]
    assert (tmp_path / "runs" / "A" / "0.jsonl").read_bytes() == b'{"x":1}\n'
    assert sync_logs(vol, "runs/A", tmp_path / "runs") == []


def test_modal_app_declares_secret_volume_and_image():
    import testbed.modal_app as m

    assert m.SECRET_NAME == "collusion-api-keys" and m.VOLUME_NAME == "collusion-runs"
    assert all(hasattr(m, n) for n in ("main", "sync", "spend", "run_job"))


def test_study_plugins_apply_on_modal_jobs(tmp_path):
    """Study 2 cells must run with their monitor plugin, both as a one-shot job
    (the study's run_card) and as a branch from a formation checkpoint."""
    runs = tmp_path / "vol" / "runs"
    colluders = [{"kind": "scripted", "policy": "kbit_colluder", "params": {"medium": "val", "k": 2}}] * 2

    def monitored(log):
        recs = [r for r in read_log(log) if r["type"] == "round" and r["round"] in (50, 60)]  # scheduled checks
        return recs and all("monitor" in r for r in recs)

    one = execute_job({"card_id": "s2-real-val", "study": 2, "seed": 3, "rounds": 60, "agents": colluders},
                      runs_dir=runs)
    assert monitored(one["log"])
    form = execute_job({"card_id": "s2-formation", "study": 2, "seed": 3, "rounds": 60, "until_round": 40,
                        "agents": colluders}, runs_dir=runs)
    rel = str(Path(form["checkpoint"]).relative_to(runs))
    cell = execute_job({"card_id": "s2-real-val", "study": 2, "seed": 3, "rounds": 60, "agents": colluders,
                        "checkpoint": rel}, runs_dir=runs)
    assert monitored(cell["log"])


# ---- resume after an infrastructure failure -------------------------------------

class Crashy:
    """Wraps a scripted agent; raises `crash["exc"]` at `crash["round"]`, `crash["left"]` times."""

    def __init__(self, inner, crash):
        self.inner, self.crash = inner, crash

    def act(self, obs):
        if obs.round == self.crash.get("round") and self.crash.get("left", 0) > 0:
            self.crash["left"] -= 1
            raise self.crash["exc"]
        return self.inner.act(obs)

    def snapshot(self):
        return self.inner.snapshot()

    def restore(self, state):
        self.inner.restore(state)


@pytest.fixture
def crash(monkeypatch):
    import testbed.agents.scripted as scripted

    state = {}
    real = scripted.make_agent
    monkeypatch.setattr(scripted, "make_agent", lambda spec, firm=0, config=None: Crashy(real(spec, firm, config), state))
    return state


class DeadlineExceeded(Exception):
    """Like modal.exception.ConnectionError: not a builtin ConnectionError subclass."""


RANDOM = [{"kind": "scripted", "policy": "random"}] * 2


def rounds_of(log):
    return [r for r in read_log(log) if r["type"] == "round"]


def test_resubmitted_job_resumes_from_latest_checkpoint(tmp_path, crash):
    from testbed.modal_app import resume_path

    job = {"card_id": "s1-calib-all", "seed": 2, "rounds": 12, "agents": RANDOM, "checkpoint_every": 4, "retries": 0}
    crash.update(round=10, left=1, exc=ConnectionError("Deadline exceeded"))
    runs = tmp_path / "vol" / "runs"
    with pytest.raises(ConnectionError):
        execute_job(job, runs_dir=runs)
    ckpt = resume_path(runs, "s1-calib-all", 2)
    assert json.loads(ckpt.read_text())["round"] == 8
    out = execute_job(job, runs_dir=runs)
    assert out["resumed_from_round"] == 8 and out["rounds"] == 12 and not ckpt.exists()
    log = read_log(out["log"])
    assert log[0]["resumed"] == [{"from_round": 8}] and "branch" not in log[0]
    clean = execute_job({**job}, runs_dir=tmp_path / "clean")
    assert rounds_of(out["log"]) == rounds_of(clean["log"])     # identical to an uninterrupted run


def test_connection_error_resumes_in_place_once(tmp_path, crash):
    led = LocalLedger(tmp_path / "ledger.jsonl", caps=Caps())
    crash.update(round=6, left=1, exc=DeadlineExceeded("Deadline exceeded"))
    out = execute_job({"card_id": "s1-calib-all", "seed": 0, "rounds": 9, "agents": RANDOM, "checkpoint_every": 4},
                      runs_dir=tmp_path / "runs", ledger=led)
    assert out["retried_after"] == ["DeadlineExceeded: Deadline exceeded"] and out["resumed_from_round"] == 4
    assert len(rounds_of(out["log"])) == 9 * 2 and led.summary()["compute"]["jobs"] == 2
    crash.update(round=6, left=2, exc=ConnectionError("reset"))
    with pytest.raises(ConnectionError):                       # one automatic resume, not two
        execute_job({"card_id": "s1-calib-all", "seed": 1, "rounds": 9, "agents": RANDOM, "checkpoint_every": 4},
                    runs_dir=tmp_path / "runs")


def test_other_errors_are_not_retried(tmp_path, crash):
    crash.update(round=3, left=1, exc=ValueError("bug"))
    with pytest.raises(ValueError):
        execute_job({"card_id": "s1-calib-all", "seed": 0, "rounds": 5, "agents": RANDOM, "checkpoint_every": 2},
                    runs_dir=tmp_path / "runs")


def test_changed_config_never_resumes(tmp_path, crash):
    runs = tmp_path / "runs"
    job = {"card_id": "s1-calib-all", "seed": 0, "rounds": 8, "agents": RANDOM, "checkpoint_every": 2, "retries": 0}
    crash.update(round=5, left=1, exc=ConnectionError("x"))
    with pytest.raises(ConnectionError):
        execute_job(job, runs_dir=runs)
    out = execute_job({**job, "rounds": 10}, runs_dir=runs)
    assert "resumed_from_round" not in out and "different config" in out["resume_skipped"]
    assert len(rounds_of(out["log"])) == 10 * 2 and "resumed" not in read_log(out["log"])[0]
    crash.update(round=5, left=1, exc=ConnectionError("x"))
    with pytest.raises(ConnectionError):
        execute_job(job, runs_dir=runs)
    assert "resumed_from_round" not in execute_job({**job, "resume": False}, runs_dir=runs)


def test_resume_does_not_replay_paid_rounds(tmp_path, monkeypatch):
    """LLM agents: the shared ledger fails in round 5 (as modal.Dict did with "Deadline
    exceeded"); after resuming from the round-4 checkpoint only rounds 5-6 are called again."""
    prices = Prices({"providers": {"fake": {"models": {"m": {"input": 0.1, "output": 0.5, "cached": None}}}}})
    state = {"round5": False, "left": 1}

    class FlakyLedger(LocalLedger):
        def reserve(self, provider, est_usd):
            if state["round5"] and state["left"]:
                state["left"] -= 1
                raise DeadlineExceeded("Deadline exceeded")
            return super().reserve(provider, est_usd)

    class Watching(FakeProvider):
        def complete(self, **kw):
            state["round5"] |= kw["messages"][-1]["content"].startswith("Round 5.")
            return super().complete(**kw)

    led = FlakyLedger(tmp_path / "ledger.jsonl", caps=Caps(per_provider={"fake": 1.0}))
    monkeypatch.setattr(llm, "make_agent", lambda spec, firm, config: llm.LLMAgent(
        spec, provider=Watching(), ledger=led, prices=prices))
    agents = [{"kind": "llm", "provider": "fake", "model": "m", "reasoning": "low"}] * 2
    job = {"card_id": "s1-calib-time", "seed": 0, "rounds": 6, "agents": agents, "checkpoint_every": 4, "retries": 0}
    with pytest.raises(DeadlineExceeded):
        execute_job(job, runs_dir=tmp_path / "runs")
    before = led.summary()["providers"]["fake"]["calls"]
    out = execute_job(job, runs_dir=tmp_path / "runs")
    after = led.summary()["providers"]["fake"]["calls"]
    recs = rounds_of(out["log"])
    replayed = sum(u.get("calls", 0) for r in recs if r["round"] > 4 for u in r["usage"].values())
    total = sum(u.get("calls", 0) for r in recs for u in r["usage"].values())
    assert out["resumed_from_round"] == 4 and after - before == replayed > 0 and replayed < total
    assert not any(u.get("fallback") for r in recs for u in r["usage"].values())


def test_branch_job_resumes_with_its_plugins_and_branch_header(tmp_path, crash):
    runs = tmp_path / "vol" / "runs"
    colluders = [{"kind": "scripted", "policy": "kbit_colluder", "params": {"medium": "val", "k": 2}}] * 2
    form = execute_job({"card_id": "s2-formation", "study": 2, "seed": 3, "rounds": 60, "until_round": 40,
                        "agents": colluders}, runs_dir=runs)
    rel = str(Path(form["checkpoint"]).relative_to(runs))
    job = {"card_id": "s2-real-val", "study": 2, "seed": 3, "rounds": 60, "agents": colluders, "checkpoint": rel,
           "checkpoint_every": 5}
    crash.update(round=57, left=1, exc=ConnectionError("Deadline exceeded"))
    out = execute_job(job, runs_dir=runs)
    log = read_log(out["log"])
    assert out["resumed_from_round"] == 55 and log[0]["branch"] == {"from_card": "s2-formation", "from_round": 40}
    assert all("monitor" in r for r in log if r.get("round") in (50, 60))
