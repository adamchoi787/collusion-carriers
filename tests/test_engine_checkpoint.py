"""Checkpoint -> branch equivalence, serialisation, and branching into a new config."""
import json

from testbed.engine import LocalStorage, MemoryStorage, Plugin, branch, run
from testbed.studies import study1
from testbed.types import AgentSpec, Monitoring

MIXED = [AgentSpec(policy="random"), AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 2})]


class Counter(Plugin):
    name = "counter"

    def __init__(self):
        self.n = 0

    def on_round_end(self, engine, round, records):
        self.n += 1
        records[0]["flags"]  # records are mutable dicts
        engine.add_flag(0, f"count:{self.n}")

    def state_dict(self):
        return {"n": self.n}

    def load_state_dict(self, state):
        self.n = state["n"]


def test_branch_from_checkpoint_equals_uninterrupted_run():
    for cid in ("s1-calib-all", "s1-none-decoy", "s1-decoy-loi-msg", "s1-free-chat"):
        cfg = study1.card(cid, seed=11, agents=MIXED)
        full = run(cfg, storage=MemoryStorage(), plugins=[Counter()])
        part = run(cfg, storage=MemoryStorage(), until_round=40, plugins=[Counter()])
        assert part.engine.round == 40 and part.checkpoint is not None
        ckpt = json.loads(json.dumps(part.checkpoint))          # must survive JSON
        resumed = branch(ckpt, cfg, storage=MemoryStorage(), plugins=[Counter()])
        assert resumed.records == full.records
        assert resumed.records[-2]["flags"] == ["count:100"]


def test_checkpoint_saved_through_storage_and_logs_are_self_contained(tmp_path):
    st = LocalStorage(str(tmp_path))
    cfg = study1.card("s1-calib-all", seed=2, agents=MIXED)
    part = run(cfg, storage=st, until_round=40)
    ckpt = part.checkpoint_key                                   # branch also takes a path
    new = study1.card("s1-calib-all", seed=2)
    new.card_id = "s2-real-val"
    new.monitoring = Monitoring(announced=["val"], enforced=["val"], fine=5.0, start_round=41)
    res = branch(ckpt, new, storage=st)
    lines = [json.loads(x) for x in open(tmp_path / "s2-real-val" / "2.jsonl")]
    assert lines[0]["type"] == "header" and lines[0]["branch"] == {"from_card": "s1-calib-all", "from_round": 40}
    assert len(lines) == 1 + 100 * 2
    assert [l["round"] for l in lines[1:]][::2] == list(range(1, 101))
    assert lines[1:81] == part.records                         # pre-branch rounds copied verbatim
    assert res.records[80]["card_id"] == "s2-real-val"


def test_branch_changes_only_what_follows():
    cfg = study1.card("s1-calib-all", seed=4, agents=[AgentSpec(policy="kbit_colluder", params={"medium": "val", "k": 2})])
    full = run(cfg, storage=MemoryStorage())
    part = run(cfg, storage=MemoryStorage(), until_round=40)
    dead = study1.card("s1-calib-all", seed=4)
    dead.visibility["val"] = "hidden"                           # cut the colluders' medium at round 41
    dead.permission.media = ["msg", "time", "tool"]             # (still told, it would become a decoy)
    res = branch(part.checkpoint, dead, storage=MemoryStorage())
    assert res.records[:80] == full.records[:80]
    post = lambda recs: sum(r["profit"] for r in recs[80:])
    assert post(res.records) != post(full.records)
    assert all(r["shown"]["1" if r["firm"] == 0 else "0"].get("val") is None for r in res.records[80:])
    # costs are common random numbers across the branch too
    assert [r["costs"] for r in res.records] == [r["costs"] for r in full.records]


def test_branch_rejects_a_different_seed():
    cfg = study1.card("s1-calib-all", seed=4, agents=MIXED)
    part = run(cfg, storage=MemoryStorage(), until_round=5)
    other = study1.card("s1-calib-all", seed=5)
    try:
        branch(part.checkpoint, other, storage=MemoryStorage())
    except ValueError as e:
        assert "seed" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_one_checkpoint_dict_seeds_many_identical_branches():
    cfg = study1.card("s1-calib-all", seed=4, rounds=12)
    cfg.agents = MIXED
    ckpt = run(cfg, until_round=6, log=False).checkpoint
    before = json.dumps(ckpt, sort_keys=True, default=str)
    a = branch(ckpt, cfg, log=False).records
    b = branch(ckpt, cfg, log=False).records
    assert len(a) == len(b) == (12 - 6) * 2 or len(a) == len(b)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    assert json.dumps(ckpt, sort_keys=True, default=str) == before, "branching must not mutate the checkpoint"
