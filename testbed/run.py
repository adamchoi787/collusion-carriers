"""Run one card for one seed.

    python -m testbed.run --card s1-calib-time --seed 0 --agents scripted:honest
    python -m testbed.run --card s1-calib-val --seed 0 --agents scripted:kbit_colluder:medium=val,k=2
    python -m testbed.run --config card.yaml --seed 3 --agents scripted:honest scripted:random
    python -m testbed.run --list
    python -m testbed.run --card s1-calib-all --dump-yaml

One --agents value is used for every firm; otherwise give one per firm. The log goes to
<out>/<card_id>/<seed>.jsonl (default out: runs/). --until-round r stops after round r and
saves a checkpoint next to the log.
"""
from __future__ import annotations

import argparse
import sys

from .engine import LocalStorage, config_to_yaml, load_config, parse_agent_arg, run
from .studies import study1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m testbed.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--card", help="Study 1 card id (see --list)")
    src.add_argument("--config", help="path to a YAML Config")
    src.add_argument("--list", action="store_true", help="list Study 1 card ids")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--agents", nargs="+", help="agent specs, e.g. scripted:honest")
    ap.add_argument("--rounds", type=int, help="override the number of rounds")
    ap.add_argument("--until-round", type=int, help="stop after this round and save a checkpoint")
    ap.add_argument("--out", default="runs", help="log root (default: runs)")
    ap.add_argument("--dump-yaml", action="store_true", help="print the card's config as YAML and exit")
    args = ap.parse_args(argv)

    if args.list:
        for cid in study1.CARD_IDS:
            print(f"{cid}\t{study1.TIER[cid]}")
        return 0
    if args.card:
        cfg = study1.card(args.card, seed=args.seed, rounds=args.rounds)
    elif args.config:
        cfg = load_config(args.config)
        cfg.seed = args.seed
        if args.rounds:
            cfg.rounds = args.rounds
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
    result = run(cfg, storage=storage, until_round=args.until_round)
    firms = cfg.n_firms
    mean_profit = sum(r["profit"] for r in result.records) / max(1, len(result.records))
    print(f"{cfg.card_id} seed={cfg.seed} rounds={result.engine.round} firms={firms} "
          f"mean profit/firm/round={mean_profit:.3f} -> {storage.log_path(cfg.card_id, cfg.seed)}")
    if result.checkpoint_key:
        print(f"checkpoint: {result.checkpoint_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
