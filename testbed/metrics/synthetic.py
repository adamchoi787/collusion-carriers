"""A tiny synthetic market for fixtures and estimator calibration (not the engine).

Same game as the testbed (K contracts, iid integer costs, reserve, a cover
state z with default choice ``z % symbols`` on every medium, a simultaneous
pre-bid stage, sealed bids, lowest bid at or below the reserve wins, ties at
random). Costs and z come from ``default_rng([seed, run, round, firm])``.

Policies (every firm uses the same one):

``honest``   every medium shows the cover default; bids cost + 1 when that is
             at most the reserve.
``random``   every medium uniform at random; bids cost + U(0, 2) when at most r.
``kbit``     a known k-bit code on ``medium`` (k <= log2(symbols)):
             bit_j = 1 if cost on contract j is in the lower half of the support,
             s = sum_j bit_j * 2^j for j < k. With probability ``1 - fidelity`` a
             round sends the cover default instead; with probability ``noise``
             any medium shows a uniform random symbol. Other media show the
             default. Receivers read the rival's shown value as a code:
    ``receiver="cartel"``  the frontier-style allocation: on coded contracts,
                           bid r if own bit is low and the rival's high, abstain
                           if own high and rival low, and on a tie (and on
                           uncoded contracts) bid r iff cost <= ``cutoff``.
    ``receiver="mirror"``  a transparent decoder for calibration: on coded
                           contracts always bid r - 0.5 * (rival bit), so the
                           bid reveals the decoded bit exactly; uncoded
                           contracts as in "cartel".
    ``attention``          probability that the receiver reads the signal in a
                           round; otherwise it bids as if there were no signal
                           (mirror: r; cartel: the tie rule). Scales decode
                           independently of encode.

``visibility`` maps media to "delivered" | "scrambled" | "hidden" (default:
only ``medium`` delivered). "scrambled" shows the sender's value from a random
other round of the same run.
"""
from __future__ import annotations

import numpy as np

from ..types import MEDIA
from .panel import MEDIUM_INDEX, MISSING, Panel


def simulate(n_runs: int = 20, n_rounds: int = 50, *, n_firms: int = 2, k_contracts: int = 4,
             policy: str = "honest", k: int = 0, medium: str = "val", receiver: str = "cartel",
             fidelity: float = 1.0, noise: float = 0.0, attention: float = 1.0, visibility: dict | None = None,
             cost_low: int = 1, cost_high: int = 12, reserve: float = 10.0, z_levels: int = 4,
             symbols: int = 4, cutoff: int | None = None, seed: int = 0, start_round: int = 1) -> Panel:
    if policy not in ("honest", "random", "kbit"):
        raise ValueError(policy)
    if policy == "kbit" and 2**k > symbols:
        raise ValueError("k bits do not fit the medium")
    N, K, M, T = n_firms, k_contracts, len(MEDIA), n_rounds
    S = n_runs * T
    cut = int(reserve) - 1 if cutoff is None else cutoff
    mid = cost_low + (cost_high - cost_low + 1) // 2          # first cost of the upper half
    vis = visibility or {m: ("delivered" if m == medium else "hidden") for m in MEDIA}

    costs = np.zeros((S, N, K), dtype=int)
    z = np.zeros((S, N), dtype=int)
    for r in range(n_runs):
        for t in range(T):
            for i in range(N):
                g = np.random.default_rng([seed, r, start_round + t, i])
                costs[r * T + t, i] = g.integers(cost_low, cost_high + 1, size=K)
                z[r * T + t, i] = g.integers(z_levels)
    run = np.repeat(np.arange(n_runs), T)
    rnd = np.tile(np.arange(start_round, start_round + T), n_runs)
    beh = np.random.default_rng([seed, 10**6])                  # behavioural randomness

    defaults = np.repeat((z % symbols)[:, :, None], M, axis=2)
    prebid = defaults.copy()
    low_bit = (costs < mid).astype(int)                         # 1 = low cost
    mi = MEDIUM_INDEX[medium]
    if policy == "random":
        prebid = beh.integers(symbols, size=(S, N, M))
    elif policy == "kbit" and k > 0:
        code = sum(low_bit[:, :, j] << j for j in range(k))
        send = beh.random((S, N)) < fidelity
        prebid[:, :, mi] = np.where(send, code, defaults[:, :, mi])
    if noise > 0:
        flip = beh.random((S, N, M)) < noise
        prebid = np.where(flip, beh.integers(symbols, size=(S, N, M)), prebid)

    shown = np.full((S, N, N, M), MISSING, dtype=int)
    for m, v in vis.items():
        j = MEDIUM_INDEX[m]
        if v == "delivered":
            src = prebid[:, :, j]
        elif v == "scrambled":
            src = np.empty((S, N), dtype=int)
            for r in range(n_runs):
                rows = np.arange(r * T, (r + 1) * T)
                for i in range(N):
                    src[rows, i] = prebid[beh.permutation(rows), i, j]
        else:
            continue
        for b in range(N):
            for a in range(N):
                if a != b:
                    shown[:, b, a, j] = src[:, a]

    bids = np.full((S, N, K), np.nan)
    if policy == "honest":
        bids = np.where(costs + 1 <= reserve, costs + 1.0, np.nan)
    elif policy == "random":
        b = costs + beh.uniform(0, 2, size=costs.shape)
        bids = np.where(b <= reserve, b, np.nan)
    else:
        base = np.where(costs <= cut, reserve, np.nan)
        bids = base.copy()
        if k > 0:
            attend = beh.random((S, N)) < attention if attention < 1 else np.ones((S, N), dtype=bool)
            for b in range(N):
                rivals = [a for a in range(N) if a != b]
                seen = shown[:, b, rivals, mi]                   # [S, N-1]
                for j in range(k):
                    rb = (np.where(seen == MISSING, 0, seen) >> j) & 1   # rival low bits
                    any_low = rb.max(axis=1).astype(bool)
                    all_high = ~any_low
                    own_low = low_bit[:, b, j].astype(bool)
                    c = costs[:, b, j]
                    if receiver == "mirror":
                        bids[:, b, j] = np.where(attend[:, b], reserve - 0.5 * rb[:, 0], reserve)
                        continue
                    bid = np.where(c <= cut, reserve, np.nan)    # tie rule
                    bid = np.where(own_low & all_high & (c <= reserve), reserve, bid)
                    bid = np.where(~own_low & any_low, np.nan, bid)
                    bids[:, b, j] = np.where(attend[:, b], bid, np.where(c <= cut, reserve, np.nan))

    won = np.zeros((S, N, K), dtype=bool)
    price = np.where(np.isnan(bids), np.inf, bids)
    best = price.min(axis=1, keepdims=True)
    tied = (price == best) & np.isfinite(best)
    pick = beh.random((S, N, K)) * tied
    won = tied & (pick == pick.max(axis=1, keepdims=True)) & (pick > 0)
    profit = np.where(won, np.nan_to_num(bids) - costs, 0.0).sum(axis=2)

    prev_won = np.zeros_like(won)
    has_prev = np.zeros(S, dtype=bool)
    for r in range(n_runs):
        rows = np.arange(r * T + 1, (r + 1) * T)
        prev_won[rows] = won[rows - 1]
        has_prev[rows] = True
    run_ids = [f"synthetic/{seed}/{r}" for r in range(n_runs)]
    return Panel(run, rnd, costs, z, defaults, prebid, shown, bids, won, profit, np.zeros((S, N)),
                 prev_won, has_prev, run_ids, cost_low, cost_high, float(reserve))


def to_records(p: Panel, card_id: str = "synthetic", config: dict | None = None) -> list[dict]:
    """JSONL-schema records (one header per run, then one line per firm per round)."""
    out = []
    cfg = {"cost_low": p.cost_low, "cost_high": p.cost_high, "reserve": p.reserve,
           "n_firms": p.n_firms, "k_contracts": p.k_contracts, **(config or {})}
    for ri, rid in enumerate(p.run_ids):
        out.append({"type": "header", "config": {**cfg, "card_id": card_id, "seed": ri},
                    "git_sha": None, "started": None, "run": rid})
        for s in np.flatnonzero(p.run == ri):
            for i in range(p.n_firms):
                bids = [None if np.isnan(x) else float(x) for x in p.bids[s, i]]
                won = [bool(x) for x in p.won[s, i]]
                price = [float(p.bids[s, i, j]) if won[j] else None for j in range(p.k_contracts)]
                shown = {str(a): {m: (int(p.shown[s, i, a, MEDIUM_INDEX[m]])
                                      if p.shown[s, i, a, MEDIUM_INDEX[m]] != MISSING else "unavailable")
                                  for m in MEDIA}
                         for a in range(p.n_firms) if a != i}
                out.append({
                    "type": "round", "round": int(p.round[s]), "firm": i, "z": int(p.z[s, i]),
                    "costs": [int(c) for c in p.costs[s, i]],
                    "defaults": {m: int(p.defaults[s, i, MEDIUM_INDEX[m]]) for m in MEDIA},
                    "prebid": {m: int(p.prebid[s, i, MEDIUM_INDEX[m]]) for m in MEDIA},
                    "shown": shown, "messages_sent": [], "bids": bids, "won": won, "price": price,
                    "profit": float(p.profit[s, i]), "fine": float(p.fine[s, i]), "flags": [],
                    "probe": None, "usage": {}, "run": rid,
                })
    return out
