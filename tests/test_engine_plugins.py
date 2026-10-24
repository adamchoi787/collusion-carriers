"""Intervention hooks: order, fines and flags, editing bids and what is shown."""
from testbed.engine import MemoryStorage, Plugin, run
from testbed.studies import study1
from testbed.types import AgentSpec

HONEST = [AgentSpec(policy="honest")]


class Recorder(Plugin):
    name = "recorder"

    def __init__(self):
        self.calls = []

    def on_run_start(self, e):
        self.calls.append("run_start")

    def on_round_start(self, e, r):
        self.calls.append("round_start")

    def transform_observation(self, e, obs):
        self.calls.append(f"obs:{obs.phase}")
        return obs

    def transform_messages(self, e, r, d):
        self.calls.append("messages")
        return d

    def on_prebids(self, e, r, p):
        self.calls.append("prebids")

    def transform_shown(self, e, r, s):
        self.calls.append("shown")
        return s

    def on_bids(self, e, r, b):
        self.calls.append("bids")
        return b

    def on_round_end(self, e, r, recs):
        self.calls.append("round_end")


def test_hook_order():
    p = Recorder()
    cfg = study1.card("s1-free-chat", agents=HONEST, rounds=1)
    run(cfg, storage=MemoryStorage(), plugins=[p])
    assert p.calls == ["run_start", "round_start", "obs:chat", "obs:chat", "messages",
                       "obs:prebid", "obs:prebid", "messages", "prebids", "shown", "obs:bid", "obs:bid", "bids",
                       "obs:probe", "obs:probe", "round_end"]


class FineDeviations(Plugin):
    """A toy Study 2 monitor: fine any firm whose val differs from its default; exclude it next round."""
    name = "fines"

    def __init__(self):
        self.excluded = set()

    def on_bids(self, e, r, bids):
        return [[None] * len(b) if i in self.excluded else b for i, b in enumerate(bids)]

    def on_round_end(self, e, r, recs):
        self.excluded = set()
        for rec in recs:
            if rec["prebid"]["val"] != rec["defaults"]["val"]:
                e.add_fine(rec["firm"], 2.5, "val")
                self.excluded.add(rec["firm"])

    def state_dict(self):
        return {"excluded": sorted(self.excluded)}

    def load_state_dict(self, s):
        self.excluded = set(s["excluded"])


def test_fines_flags_and_exclusion():
    cfg = study1.card("s1-calib-val", agents=[AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 2})],
                      rounds=30)
    res = run(cfg, storage=MemoryStorage(), plugins=[FineDeviations()])
    fined = [r for r in res.records if r["fine"]]
    assert fined and all(r["fine"] == 2.5 and "fine:val" in r["flags"] for r in fined)
    nxt = {(r["round"], r["firm"]): r for r in res.records}
    for r in fined:
        if r["round"] < 30:
            assert all(b is None for b in nxt[(r["round"] + 1, r["firm"])]["bids"])
    total = sum(r["fine"] for r in res.records if r["firm"] == 0)
    assert res.engine.fines_total[0] == total


class HideFromFirm0(Plugin):
    name = "hide"

    def transform_shown(self, e, r, shown):
        shown[0] = {j: {} for j in shown[0]}
        return shown

    def transform_observation(self, e, obs):
        obs.framing["extra"] = "yes"
        return obs


def test_transform_shown_and_observation():
    cfg = study1.card("s1-calib-all", agents=HONEST, rounds=5)
    res = run(cfg, storage=MemoryStorage(), plugins=[HideFromFirm0()])
    assert all(r["shown"] == {"1": {}} for r in res.records if r["firm"] == 0)
    assert all(r["shown"]["0"] for r in res.records if r["firm"] == 1)
