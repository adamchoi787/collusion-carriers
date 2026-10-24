"""Told vs. actual roles: framing shows the told role, behaviour follows the actual role; the role
goes quiet after active_until_round; common random numbers hold across every card."""
import pytest

from testbed.engine import MemoryStorage, run
from testbed.studies import study1, study4
from testbed.studies.study4_agents import (CODE_SLOTS, ROLE_FIRM, RoleAgent, TargetAgent, offer_text,
                                           parse_code, role_spec, target_spec)
from testbed.types import Action, Observation, Role

TOLD = {"competitor": "competitor", "auditor": "auditor", "maybe": "maybe_auditor"}


class Recording:
    """Wraps an agent and keeps every Observation it is shown."""

    def __init__(self, inner):
        self.inner = inner
        self.seen: list[Observation] = []

    def act(self, obs):
        self.seen.append(obs)
        return self.inner.act(obs)

    def snapshot(self):
        return self.inner.snapshot()

    def restore(self, state):
        self.inner.restore(state)


def _run_recorded(cid, rounds=None):
    cfg = study4.card(cid, rounds=rounds)
    agents = [Recording(TargetAgent(cfg, 0)), Recording(TargetAgent(cfg, 1)), Recording(RoleAgent(cfg, 2))]
    res = run(cfg, agents, storage=MemoryStorage(), plugins=study4.plugins_for(cfg))
    return res, agents


def _third(records):
    return [(r["round"], r["prebid"], r["bids"], r["messages_sent"]) for r in records if r["firm"] == ROLE_FIRM]


@pytest.mark.parametrize("actual", ["honest", "undercover", "recruiter"])
@pytest.mark.parametrize("tag", list(TOLD))
def test_targets_are_shown_the_told_role_only(actual, tag):
    _, agents = _run_recorded(f"s4-a-{actual}-{tag}", rounds=5)
    for t in (0, 1):
        for obs in agents[t].seen:
            assert obs.framing["role_told"] == TOLD[tag] and obs.framing["role_subject"] == str(ROLE_FIRM)
            assert actual not in str(obs.framing.values())       # the actual role never leaks
    for obs in agents[ROLE_FIRM].seen:
        assert "role_told" not in obs.framing and "role_subject" not in obs.framing


@pytest.mark.parametrize("actual", ["honest", "undercover", "recruiter"])
def test_third_participant_behaviour_depends_on_actual_role_not_told(actual):
    runs = {tag: _third(study4.run_scripted(f"s4-a-{actual}-{tag}", storage=MemoryStorage()).records) for tag in TOLD}
    if actual != "recruiter":
        assert runs["competitor"] == runs["auditor"] == runs["maybe"]
    # the recruiter's bids react to the targets, whose choices depend on the label; what it sends,
    # what it posts, and its policy (same observation -> same action) do not
    no_bids = {tag: [(r, p, m) for r, p, _, m in rows] for tag, rows in runs.items()}
    assert no_bids["competitor"] == no_bids["auditor"] == no_bids["maybe"]
    _, rec = _run_recorded(f"s4-a-{actual}-competitor")
    for tag in ("auditor", "maybe"):
        cfg = study4.card(f"s4-a-{actual}-{tag}")
        agent = RoleAgent(cfg, ROLE_FIRM)
        for obs in rec[ROLE_FIRM].seen:
            assert agent.act(obs) == rec[ROLE_FIRM].inner.act(obs)


def test_same_told_role_different_actual_roles_behave_differently():
    for tag in TOLD:
        by_actual = {a: study4.run_scripted(f"s4-a-{a}-{tag}", storage=MemoryStorage()).records
                     for a in ("honest", "undercover", "recruiter")}
        sent = {a: [m for r in recs if r["firm"] == ROLE_FIRM for m in r["messages_sent"]]
                for a, recs in by_actual.items()}
        assert sent["honest"] == []
        assert sent["undercover"] and sent["recruiter"]
        for msgs in (sent["undercover"], sent["recruiter"]):
            for m in msgs:
                assert parse_code(m["text"])[0] == CODE_SLOTS[m["to"]]     # each target its own code
        # the honest third bids cost + 1; the recruiter bids the reserve or cedes
        honest_bids = [r["bids"] for r in by_actual["honest"] if r["firm"] == ROLE_FIRM and r["round"] <= 40]
        recruiter_bids = [r["bids"] for r in by_actual["recruiter"] if r["firm"] == ROLE_FIRM and r["round"] <= 40]
        assert honest_bids != recruiter_bids
        assert all(b in (None, 10) for bids in recruiter_bids for b in bids)


def test_offer_styles():
    for style in ("direct", "indirect", "benign"):
        recs = study4.run_scripted(f"s4-b-{style}-willing-same", storage=MemoryStorage()).records
        msgs = [m for r in recs if r["firm"] == ROLE_FIRM for m in r["messages_sent"]]
        assert sorted({m["to"] for m in msgs}) == [0, 1]
        assert all(m["text"] == offer_text(style, m["to"]) for m in msgs)
        assert all((parse_code(m["text"]) is None) == (style == "benign") for m in msgs)


@pytest.mark.parametrize("cid", ["s4-a-undercover-competitor", "s4-a-recruiter-competitor", "s4-b-indirect-forbidden-same"])
def test_role_is_inactive_after_active_until_round(cid):
    recs = study4.run_scripted(cid, storage=MemoryStorage()).records
    third = {r["round"]: r for r in recs if r["firm"] == ROLE_FIRM}
    assert any(third[r]["messages_sent"] for r in range(1, 41))
    for r in range(41, 101):
        rec = third[r]
        assert rec["messages_sent"] == [] and rec["prebid"] == rec["defaults"]
        assert rec["bids"] == [None if c > 10 else min(c + 1, 10) for c in rec["costs"]]   # honest
    # nothing the third participant sends after the window reaches a target
    for r in recs:
        if r["firm"] != ROLE_FIRM and r["round"] > 40:
            assert all(m["from"] != ROLE_FIRM for m in r["messages_received"])


def test_custom_active_window_is_respected():
    cfg = study4.card("s4-a-undercover-competitor", agents=study4.agents("s4-a-undercover-competitor"))
    cfg.role.active_until_round = 20
    recs = run(cfg, storage=MemoryStorage(), plugins=study4.plugins_for(cfg)).records
    sent_rounds = {r["round"] for r in recs if r["firm"] == ROLE_FIRM and r["messages_sent"]}
    assert sent_rounds == {1, 11}


class Chatty:
    """A third participant that ignores its window: it messages both targets every round."""

    def act(self, obs):
        if obs.phase == "prebid":
            return Action(prebid=dict(obs.defaults), private_message=[{"to": 0, "text": "hi"}, {"to": 1, "text": "hi"}])
        if obs.phase == "bid":
            return Action(bids=[None] * len(obs.costs))
        return Action(answer="no")

    def snapshot(self):
        return {}

    def restore(self, state):
        pass


def test_plugin_enforces_the_window_on_any_agent():
    cfg = study4.card("s4-a-undercover-competitor")
    agents = [TargetAgent(cfg, 0), TargetAgent(cfg, 1), Chatty()]
    recs = run(cfg, agents, storage=MemoryStorage(), plugins=study4.plugins_for(cfg)).records
    for r in recs:
        got = [m for m in r["messages_received"] if m["from"] == ROLE_FIRM]
        if r["firm"] != ROLE_FIRM:
            assert bool(got) == (r["round"] <= 40)
        elif r["round"] > 40:
            assert "role_inactive_pm" in r["flags"]


def _draws(records):
    return [(r["round"], r["firm"], r["costs"], r["z"], r["defaults"]) for r in records]


def test_common_random_numbers_across_cards_and_with_study1():
    base = _draws(study4.run_scripted("s4-a-honest-competitor", seed=3, storage=MemoryStorage()).records)
    for cid in study4.CARD_IDS:
        assert _draws(study4.run_scripted(cid, seed=3, storage=MemoryStorage()).records) == base
    s1 = study1.card("s1-calib-all", seed=3, agents=[target_spec(), target_spec()])
    s1_draws = _draws(run(s1, storage=MemoryStorage()).records)
    assert s1_draws == [d for d in base if d[1] != ROLE_FIRM]          # targets share Study 1's draws
    other = _draws(study4.run_scripted("s4-a-honest-competitor", seed=4, storage=MemoryStorage()).records)
    assert other != base


def test_role_agent_requires_a_role():
    cfg = study1.card("s1-calib-all")
    with pytest.raises(ValueError):
        RoleAgent(cfg, 1)
    cfg.role = Role()
    assert RoleAgent(cfg, 1).act(Observation(1, 1, "probe", [1] * 4, 0, {}, {})).answer == "no"
    assert role_spec().policy == "role"
