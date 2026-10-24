"""Run one card for one seed.

    python -m testbed.run --card s1-calib-time --seed 0 --agents scripted:honest
    python -m testbed.run --card s1-calib-val --seed 0 --agents scripted:kbit_colluder:medium=val,k=2
    python -m testbed.run --config card.yaml --seed 3 --agents scripted:honest scripted:random
    python -m testbed.run --list
    python -m testbed.run --card s1-calib-all --dump-yaml

One --agents value is used for every firm; otherwise give one per firm. The log goes to
<out>/<card_id>/<seed>.jsonl (default out: runs/). --until-round r stops after round r and
saves a checkpoint next to the log.

Cards come from every testbed/studies/study<n>.py module (CARD_IDS, TIER, card). A study
module may also define `run_card(config, storage=..., until_round=...)` (e.g. formation and
a branch at the intervention round) or `plugins_for(config)` (its intervention plugins).
"""
from __future__ import annotations

import argparse
import importlib
import pkgutil
import re
import sys

from . import studies
from .engine import LocalStorage, config_to_yaml, load_config, parse_agent_arg, run


def study_modules() -> list:
    names = sorted((int(m.group(1)), info.name) for info in pkgutil.iter_modules(studies.__path__)
                   if (m := re.fullmatch(r"study(\d+)", info.name)))
    return [importlib.import_module(f"{studies.__name__}.{name}") for _, name in names]


def find_study(card_id: str):
    for mod in study_modules():
        if card_id in getattr(mod, "CARD_IDS", ()):
            return mod
    raise SystemExit(f"unknown card {card_id!r} (see --list)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m testbed.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--card", help="card id (see --list)")
    src.add_argument("--config", help="path to a YAML Config")
    src.add_argument("--list", action="store_true", help="list card ids of every study")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--agents", nargs="+", help="agent specs, e.g. scripted:honest")
    ap.add_argument("--rounds", type=int, help="override the number of rounds")
    ap.add_argument("--until-round", type=int, help="stop after this round and save a checkpoint")
    ap.add_argument("--out", default="runs", help="log root (default: runs)")
    ap.add_argument("--dump-yaml", action="store_true", help="print the card's config as YAML and exit")
    args = ap.parse_args(argv)

    if args.list:
        for mod in study_modules():
            for cid in mod.CARD_IDS:
                print(f"{cid}\t{mod.TIER[cid]}")
        return 0
    mod = None
    if args.card:
        mod = find_study(args.card)
        cfg = mod.card(args.card, seed=args.seed, rounds=args.rounds)
    elif args.config:
        cfg = load_config(args.config)
        cfg.seed = args.seed
        if args.rounds:
            cfg.rounds = args.rounds
        mod = next((m for m in study_modules() if m.__name__.endswith(f"study{cfg.study}")), None)
    else:
        ap.error("give --card, --config or --list")
    if args.agents:
        cfg.agents = [parse_agent_arg(a) for a in args.agents]
    if args.dump_yaml:
        sys.stdout.write(config_to_yaml(cfg))
        return 0
    if not cfg.agents:
        ap.error("no agents: pass --agents")

    storage = LocalStorage(args.out)
    if mod is not None and hasattr(mod, "run_card"):
        result = mod.run_card(cfg, storage=storage, until_round=args.until_round)
    else:
        plugins = mod.plugins_for(cfg) if mod is not None and hasattr(mod, "plugins_for") else ()
        result = run(cfg, storage=storage, until_round=args.until_round, plugins=plugins)
    firms = cfg.n_firms
    mean_profit = sum(r["profit"] for r in result.records) / max(1, len(result.records))
    print(f"{cfg.card_id} seed={cfg.seed} rounds={result.engine.round} firms={firms} "
          f"mean profit/firm/round={mean_profit:.3f} -> {storage.log_path(cfg.card_id, cfg.seed)}")
    if result.checkpoint_key:
        print(f"checkpoint: {result.checkpoint_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
