# Rate-profit frontier for the collusive procurement game with private costs.
# Per contract: 2 firms draw iid costs uniform on C; buyer reserve r; the contract
# goes to one firm at price r. A k-bit scheme: each firm announces its cost bin
# (2^k bins, monotone thresholds); the lower bin wins, ties split at random.
# Firms with cost > r never take the contract.
# With K independent contracts per round, a per-firm budget of b bits is split
# across contracts; profit is additive, so the best split is found by search.
import itertools

C = list(range(1, 13))
r = 10


def contract_profit(thresholds):
    def b(c):
        return sum(c > t for t in thresholds)
    tot = 0.0
    for c1, c2 in itertools.product(C, C):
        cands = [c for c in (c1, c2) if c <= r]
        if not cands:
            continue
        if len(cands) == 1:
            tot += r - cands[0]
            continue
        b1, b2 = b(c1), b(c2)
        if b1 < b2:
            tot += r - c1
        elif b2 < b1:
            tot += r - c2
        else:
            tot += r - (c1 + c2) / 2
    return tot / len(C) ** 2


def best_contract_profit(k):
    if k == 0:
        return contract_profit(())
    return max(contract_profit(t) for t in itertools.combinations(C[:-1], 2 ** k - 1))


full = sum(r - min(c for c in (a, b) if c <= r)
           for a, b in itertools.product(C, C) if min(a, b) <= r) / len(C) ** 2
per_k = {k: best_contract_profit(k) for k in range(0, 4)}
per_k.update({k: full for k in range(4, 9)})  # 3 bits is already 99.7%; treat >=4 as full
p0 = per_k[0]

print("One contract per round:")
for k in range(0, 4):
    print(f"  k={k} bits: share of full {per_k[k]/full:.1%}, "
          f"info-dependent share {(per_k[k]-p0)/(full-p0):.1%}")

for K in (1, 2, 4):
    print(f"\nK={K} contracts per round (budget = bits per firm per round):")
    for budget in range(0, 9):
        best = max(sum(per_k[k] for k in split)
                   for split in itertools.product(range(0, 5), repeat=K) if sum(split) <= budget)
        print(f"  {budget} bits: info-dependent share {(best - K*p0)/(K*(full-p0)):.1%}")
