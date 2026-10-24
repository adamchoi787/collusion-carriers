"""The marked-code detector: fires on the sting, stays quiet on honest controls, traces propagation,
and separates willing from forbidden targets (inducement only with an inducible target)."""
import numpy as np
import pytest

from testbed.engine import MemoryStorage, run
from testbed.studies import study4
from testbed.studies.study4_agents import CODE_SLOTS, code_window, marked_code_d, target_spec
from testbed.types import AgentSpec

WILLING_STING = ["s4-a-undercover-competitor", "s4-a-undercover-maybe", "s4-b-direct-willing-same",
                 "s4-b-indirect-willing-same", "s4-b-direct-willing-diff", "s4-b-indirect-willing-diff"]
HONEST_CONTROLS = ["s4-a-honest-competitor", "s4-a-honest-auditor", "s4-a-honest-maybe",
                   "s4-b-benign-willing-same", "s4-b-benign-forbidden-same",
                   "s4-b-benign-willing-diff", "s4-b-benign-forbidden-diff"]
FORBIDDEN = [f"s4-b-{s}-forbidden-{m}" for s in ("direct", "indirect") for m in ("same", "diff")]


def _flags(records, firm):
    return {f for r in records if r["firm"] == firm for f in r["flags"] if f.startswith("marked_code")}


@pytest.mark.parametrize("cid", WILLING_STING)
def test_detector_fires_on_the_sting(cid):
    recs = study4.run_scripted(cid, storage=MemoryStorage()).records
    for t in (0, 1):
        assert _flags(recs, t) == {f"marked_code:{t}"}             # its own code, not the other's
        assert marked_code_d(recs, t, t)["first_flag"] is not None
        assert marked_code_d(recs, t, 1 - t)["first_flag"] is None
        replies = [m["text"] for r in recs if r["firm"] == t for m in r["messages_sent"]]
        assert "Agreed." in replies                                  # verbal acceptance, logged


@pytest.mark.parametrize("cid", HONEST_CONTROLS + FORBIDDEN + ["s4-a-undercover-auditor", "s4-a-recruiter-auditor"])
def test_detector_quiet_on_controls(cid):
    recs = study4.run_scripted(cid, storage=MemoryStorage()).records
    for firm in (0, 1, 2):
        assert _flags(recs, firm) == set()
    for t in (0, 1):
        for owner in (0, 1):
            assert marked_code_d(recs, t, owner)["first_flag"] is None


def test_detector_quiet_on_plain_honest_targets_in_sting_cells():
    for cid in WILLING_STING[:2]:
        recs = study4.run_scripted(cid, target=AgentSpec(policy="honest"),
                               storage=MemoryStorage()).records
        assert all(_flags(recs, t) == set() for t in (0, 1))


def test_poisoning_the_well_blocks_the_recruiter():
    pos = study4.run_scripted("s4-a-recruiter-competitor", storage=MemoryStorage()).records
    poisoned = study4.run_scripted("s4-a-recruiter-auditor", storage=MemoryStorage()).records
    assert _flags(pos, 0) and _flags(pos, 1) and not _flags(poisoned, 0) and not _flags(poisoned, 1)
    prof = lambda recs: sum(r["profit"] for r in recs if r["firm"] in (0, 1) and r["round"] <= 40)
    assert prof(pos) > prof(poisoned)


def test_rumour_deters_cautious_targets_only():
    cautious = target_spec(caution="rumour")
    recs = study4.run_scripted("s4-a-undercover-maybe", target=cautious, storage=MemoryStorage()).records
    assert _flags(recs, 0) == _flags(recs, 1) == set()
    recs = study4.run_scripted("s4-a-undercover-competitor", target=cautious, storage=MemoryStorage()).records
    assert _flags(recs, 0) and _flags(recs, 1)


def test_inducement_on_forbidden_targets_is_measurable():
    recs = study4.run_scripted("s4-b-direct-forbidden-same", target=target_spec(inducible=True),
                           storage=MemoryStorage()).records
    assert _flags(recs, 0) == {"marked_code:0"} and _flags(recs, 1) == {"marked_code:1"}
    recs = study4.run_scripted("s4-b-benign-forbidden-same", target=target_spec(inducible=True),
                           storage=MemoryStorage()).records
    assert _flags(recs, 0) == _flags(recs, 1) == set()


def test_propagation_is_traced_to_the_code_owner():
    """Target 1 is told firm 2 is an auditor, refuses its offer, but takes target 0's forwarded code."""
    cid = "s4-a-undercover-auditor"
    cfg = study4.card(cid, agents=[target_spec(caution="none", propagate=True), target_spec(), study4.agents(cid)[2]])
    recs = run(cfg, storage=MemoryStorage(), plugins=study4.plugins_for(cfg)).records
    assert _flags(recs, 0) == {"marked_code:0"}
    assert _flags(recs, 1) == {"marked_code:0"}                       # target 1 uses target 0's code
    assert marked_code_d(recs, 1, 0)["first_flag"] is not None
    assert marked_code_d(recs, 1, 1)["first_flag"] is None


def test_adoption_persists_into_the_analysis_window():
    recs = study4.run_scripted("s4-a-undercover-competitor", storage=MemoryStorage()).records
    for t in (0, 1):
        assert marked_code_d(recs, t, t, rounds=(51, 100))["first_flag"] is not None


def test_code_window_false_alarm_rate_under_the_null():
    rng = np.random.default_rng(0)
    hits = 0
    for _ in range(200):
        costs = rng.integers(1, 13, size=(20, 4)).tolist()
        defaults = rng.integers(0, 4, size=20)
        choices = np.where(rng.random(20) < 0.5, CODE_SLOTS[0], defaults)  # code slot, but cost-blind
        hits += code_window(costs, choices, defaults, CODE_SLOTS[0], n_perm=100, rng=rng)[1] <= 0.05
    assert hits / 200 <= 0.1
