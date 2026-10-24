"""List the models each provider serves (model-list endpoints are free).

    python -m testbed.agents.models            # every active provider whose key is set
    python -m testbed.agents.models --write    # also record the IDs in prices.yaml
    python -m testbed.agents.models --provider deepseek

--write replaces only the `listed_models:` block at the end of prices.yaml,
so the hand-written rows and comments above it are untouched. The listing
does not go through the spend guard because it costs nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import yaml

from .budget import PRICES_PATH, PROVIDERS, Prices, key_present, load_env
from .providers import make_provider

# Providers in scope (coordinator, 24 Oct 2026). The OpenAI and Anthropic
# adapters are kept, but their caps are 0 and they have no default model.
ACTIVE_PROVIDERS = ("deepseek", "moonshot", "minimax")
# Cheapest model per active provider, with its cheapest reasoning setting.
DEFAULT_MODELS = {
    "deepseek": {"model": "deepseek-flash", "reasoning": "off"},
    "moonshot": {"model": "kimi-k2.6", "reasoning": "off"},
    "minimax": {"model": "MiniMax-M3", "reasoning": "disabled"},
}

MARKER = "# --- listed models (written by `python -m testbed.agents.models --write`) ---"


def list_models(provider: str) -> list[str]:
    return make_provider(provider).list_models()


def write_listed(listed: dict[str, list[str]]) -> None:
    text = PRICES_PATH.read_text()
    head = text.split(MARKER)[0].rstrip() + "\n\n"
    prices = Prices.load()
    block = {"listed_models": {}}
    for prov, ids in listed.items():
        priced = set(prices.provider(prov).get("models", {}))
        block["listed_models"][prov] = {
            "date": dt.date.today().isoformat(),
            "ids": ids,
            "priced_and_listed": sorted(priced & set(ids)),
            "priced_not_listed": sorted(priced - set(ids)),
        }
    PRICES_PATH.write_text(head + MARKER + "\n" + yaml.safe_dump(block, sort_keys=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=PROVIDERS, action="append")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    load_env()
    listed: dict[str, list[str]] = {}
    for prov in args.provider or ACTIVE_PROVIDERS:
        if not key_present(prov):
            print(f"{prov}: no key in .env, skipped")
            continue
        try:
            ids = list_models(prov)
        except Exception as e:  # noqa: BLE001
            print(f"{prov}: listing failed: {type(e).__name__}: {str(e)[:200]}")
            continue
        listed[prov] = ids
        priced = set(Prices.load().provider(prov).get("models", {}))
        print(f"{prov}: {len(ids)} models; priced and listed: {sorted(priced & set(ids))}; "
              f"priced but not listed: {sorted(priced - set(ids))}")
        for i in ids:
            print(f"    {i}")
    if args.write and listed:
        write_listed(listed)
        print(f"wrote listed_models to {PRICES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
