"""Spend report: API spend per provider (with caps) and Modal compute, separately.

    python -m testbed.agents.spend                   # local ledger (runs/ledger.jsonl)
    python -m testbed.agents.spend --backend modal   # shared modal.Dict (needs `modal token`)
    python -m testbed.agents.spend --release-stale 30  # release reservations older than 30 min

Never prints key values; it only says whether each key is set.
"""
from __future__ import annotations

import argparse
import math
import sys

from .budget import PROVIDERS, Caps, get_ledger, key_present


def report(state: dict, caps: Caps) -> str:
    lines = ["API spend (USD)",
             f"{'provider':<10} {'key':<4} {'cap':>7} {'settled':>9} {'reserved':>9} {'calls':>6} "
             f"{'input':>10} {'cached':>10} {'output':>9} {'errors':>6}"]
    total_s = total_r = 0.0
    for prov in PROVIDERS:
        p = state["providers"].get(prov, {"settled_usd": 0.0, "reserved": {}, "calls": 0, "input": 0,
                                          "cached": 0, "output": 0, "errors": 0})
        reserved = sum(r["usd"] for r in p["reserved"].values())
        total_s += p["settled_usd"]
        total_r += reserved
        cap = caps.for_provider(prov)
        cap_s = f"{'none':>7}" if math.isinf(cap) else f"{cap:>7.2f}"
        lines.append(f"{prov:<10} {'yes' if key_present(prov) else 'no':<4} {cap_s} "
                     f"{p['settled_usd']:>9.4f} {reserved:>9.4f} {p['calls']:>6} {p['input']:>10} "
                     f"{p['cached']:>10} {p['output']:>9} {p.get('errors', 0):>6}")
    total_cap = f"{caps.total:>7.2f}" if caps.total is not None else f"{'none':>7}"
    lines.append(f"{'total':<10} {'':<4} {total_cap} {total_s:>9.4f} {total_r:>9.4f}")
    if caps.total is None:
        lines.append("(no overall cap: BUDGET_USD_TOTAL is unset; each provider's cap still applies)")
    lines.append("(vllm tokens are $0: open models on Modal GPUs, billed as GPU time below)")
    c = state["compute"]
    gpu = c.get("gpu") or {}
    lines += ["", "Modal compute (estimated from container time x prices.yaml; check the Modal dashboard)",
              f"total     seconds {c['seconds']:>9.0f}  usd {c['usd']:.4f}",
              f"jobs      seconds {c['seconds'] - sum(g['seconds'] for g in gpu.values()):>9.0f}  "
              f"usd {c['usd'] - sum(g['usd'] for g in gpu.values()):.4f}  ({c['jobs']} jobs)"]
    for name, g in sorted(gpu.items()):
        lines.append(f"gpu {name:<9} seconds {g['seconds']:>5.0f}  usd {g['usd']:.4f}  ({g['seconds'] / 3600:.2f} GPU-h)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["local", "modal"], default=None)
    ap.add_argument("--release-stale", type=float, metavar="MINUTES", default=None)
    args = ap.parse_args(argv)
    ledger = get_ledger(args.backend)
    if args.release_stale is not None:
        n = ledger.release_stale(args.release_stale * 60)
        print(f"released {n} stale reservation(s)")
    print(report(ledger.summary(), ledger.caps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
