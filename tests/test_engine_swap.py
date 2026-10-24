"""The swap hook: replace an agent at a round, keep its displayed identity, optionally wipe memory."""
from testbed.engine import MemoryStorage, branch, register_agent_kind, run
from testbed.engine.framing import framing
from testbed.studies import study1
from testbed.types import Action, AgentSpec, Identity, Swap


class Diary:
    """Remembers the rounds it has played; its memory is its snapshot."""
    made = []

    def __init__(self, spec, firm):
        self.tag, self.firm, self.notes = spec.params.get("tag", "a"), firm, []
        Diary.made.append(self)

    def act(self, obs):
        if obs.phase == "prebid":
            self.notes.append(obs.round)
            return Action(prebid=dict(obs.defaults))
        if obs.phase == "bid":
            return Action(bids=[c + 1 if c < 10 else None for c in obs.costs])
        return Action()

    def snapshot(self):
        return {"notes": list(self.notes)}

    def restore(self, s):
        self.notes = list(s.get("notes", []))


register_agent_kind("diary", lambda spec, firm, cfg: Diary(spec, firm))


def _cfg(swap):
    cfg = study1.card("s1-calib-val", seed=1, agents=[AgentSpec(kind="diary", params={"tag": "a"})])
    cfg.identity = Identity(told=None, swap=swap)
    return cfg


def _new(swap):
    Diary.made = []
    res = run(_cfg(swap), storage=MemoryStorage())
    return res, Diary.made


def test_swap_replaces_agent_and_keeps_firm_identity():
    res, made = _new(Swap(at_round=41, actual="other_provider", firm=1,
                          replacement=AgentSpec(kind="diary", params={"tag": "b"})))
    assert len(made) == 3 and made[2].tag == "b"
    assert res.engine.agents[1] is made[2] and res.engine.agents[0] is made[0]
    labels = {(r["round"], r["firm"]): r["agent"] for r in res.records}
    assert labels[(40, 1)] == "diary:None/None#1" and labels[(41, 1)] == "diary:None/None#2"
    assert labels[(41, 0)] == labels[(40, 0)]
    # the rival still sees "firm 1" throughout
    assert all(set(r["shown"]) == {"1"} for r in res.records if r["firm"] == 0)
    # memory carried over (not wiped)
    assert made[2].notes == list(range(1, 101)) and made[1].notes == list(range(1, 41))


def test_swap_with_memory_wipe():
    _, made = _new(Swap(at_round=41, actual="same_model", firm=1, wipe_memory=True))
    assert made[2].notes == list(range(41, 101)) and made[2].tag == "a"


def test_sham_swap_changes_nothing_but_can_be_announced():
    res, made = _new(Swap(at_round=41, actual="none", announced=True, firm=1))
    assert len(made) == 2
    cfg = _cfg(Swap(at_round=41, actual="none", announced=True, firm=1))
    assert framing(cfg, 0, 41)["swap_announced"] == "1"
    assert "swap_announced" not in framing(cfg, 0, 40) and "swap_announced" not in framing(cfg, 1, 41)


def test_swap_applied_by_branching_at_the_intervention_round():
    Diary.made = []
    base = _cfg(None)
    part = run(base, storage=MemoryStorage(), until_round=40)
    swapped = _cfg(Swap(at_round=41, actual="same_model", firm=1, wipe_memory=True))
    swapped.card_id = "s3-covert-same-wiped"
    res = branch(part.checkpoint, swapped, storage=MemoryStorage())
    assert res.engine.agents[1].notes == list(range(41, 101))
    assert res.engine.agents[0].notes == list(range(1, 101))     # restored from the checkpoint
