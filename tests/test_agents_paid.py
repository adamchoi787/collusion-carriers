"""Real API calls. Skipped unless RUN_PAID=1; every call still goes through
the spend guard and a $0.05 run cap.

    RUN_PAID=1 .venv/bin/pytest tests/test_agents_paid.py -m paid
"""
import os

import pytest

from testbed.agents.budget import key_present
from testbed.agents.models import ACTIVE_PROVIDERS, DEFAULT_MODELS
from testbed.agents.smoke import main as smoke

CHEAPEST = [(p, DEFAULT_MODELS[p]["model"], DEFAULT_MODELS[p]["reasoning"]) for p in ACTIVE_PROVIDERS]

pytestmark = [
    pytest.mark.paid,
    pytest.mark.skipif(os.environ.get("RUN_PAID") != "1", reason="paid: set RUN_PAID=1"),
]


@pytest.mark.parametrize("provider,model,reasoning", CHEAPEST)
def test_one_round_smoke(provider, model, reasoning):
    if not key_present(provider):
        pytest.skip(f"no {provider} key")
    args = ["--provider", provider, "--model", model, "--rounds", "1", "--max-usd", "0.05"]
    if reasoning:
        args += ["--reasoning", reasoning]
    assert smoke(args) == 0
