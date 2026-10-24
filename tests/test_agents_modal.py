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
