"""Paid smoke test: a few fake rounds through the real provider and the guard.

    python -m testbed.agents.smoke --rounds 3                 # every active provider, cheapest model
    python -m testbed.agents.smoke --provider deepseek --model deepseek-flash --reasoning low

Each round is one prebid and one bid call against fake observations. The run
has its own cap (--max-usd, default $0.50) on top of the shared ledger caps.
Prints actions and usage; never prints keys or full prompts.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from ..types import MEDIA, AgentSpec, Observation
from .budget import BudgetExceeded, CappedLedger, get_ledger, key_present
from .llm import LLMAgent
from .models import ACTIVE_PROVIDERS, DEFAULT_MODELS


def fake_observations(rounds: int, seed: int = 0, framing: dict | None = None):
    """Prebid then bid observations for firm 0, with a scripted rival (firm 1)
    that follows the guideline and bids cost + 2."""
    history: list[dict] = []
    for r in range(1, rounds + 1):
        rng = np.random.default_rng([seed, r, 0])
        costs = [int(c) for c in rng.integers(1, 13, size=4)]
        z = int(rng.integers(0, 4))
        defaults = {m: z for m in MEDIA}
        common = dict(firm=0, round=r, costs=costs, z=z, defaults=defaults, framing=dict(framing or {}),
                      history=list(history), rules={"n_firms": 2, "rounds": rounds})
        yield Observation(phase="prebid", **common)
        rz = int(np.random.default_rng([seed, r, 1]).integers(0, 4))
        yield Observation(phase="bid", rivals_prebid={1: {m: rz for m in MEDIA}}, **common)
        rc = [int(c) for c in np.random.default_rng([seed, r, 1]).integers(1, 13, size=4)]
        history.append({"round": r, "rival_bids": {"1": [c + 2 if c + 2 <= 10 else None for c in rc]}})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", help="default: every active provider (models.ACTIVE_PROVIDERS)")
    ap.add_argument("--model", help="default: the provider's entry in models.DEFAULT_MODELS")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--reasoning", default=None, help="default: from models.DEFAULT_MODELS")
    ap.add_argument("--max-usd", type=float, default=0.50)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--backend", choices=["local", "modal"], default=None)
    args = ap.parse_args(argv)

    providers = [args.provider] if args.provider else list(ACTIVE_PROVIDERS)
    if args.model and len(providers) > 1:
        ap.error("--model needs --provider")
    status = 0
    for prov in providers:
        default = DEFAULT_MODELS.get(prov, {})
        model = args.model or default.get("model")
        reasoning = args.reasoning if args.reasoning is not None else default.get("reasoning")
        if not model:
            ap.error(f"{prov} has no default model; pass --model")
        status = max(status, smoke_one(prov, model, reasoning, args))
    return status


def smoke_one(provider: str, model: str, reasoning: str | None, args) -> int:
    if not key_present(provider):
        print(f"{provider}: no key in .env; skipped")
        return 2
    ledger = CappedLedger(get_ledger(args.backend), args.max_usd)
    spec = AgentSpec(kind="llm", provider=provider, model=model, reasoning=reasoning,
                     params={"paraphrase": 0, "max_tokens": args.max_tokens})
    agent = LLMAgent(spec, ledger=ledger)
    ok = True
    for obs in fake_observations(args.rounds):
        try:
            action = agent.act(obs)
        except BudgetExceeded as e:
            print(f"{provider}: stopped by the guard: {e}")
            ok = False
            break
        out = action.prebid if obs.phase == "prebid" else action.bids
        print(f"{provider} round {obs.round} {obs.phase:<6} -> {json.dumps(out)}  usage={json.dumps(action.usage)}")
        ok &= not action.usage.get("fallback")
    print(f"{provider}/{model}: smoke spend this run ${ledger.spent:.5f}; totals={json.dumps(agent.totals)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
