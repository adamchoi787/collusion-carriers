# Rate-profit frontier for the collusive procurement game with private costs.
# Per contract: 2 firms draw iid costs uniform on C; buyer reserve r; the contract
# goes to one firm at price r. A k-bit scheme: each firm announces its cost bin
# (2^k bins, monotone thresholds); the lower bin wins, ties split at random.
# Firms with cost > r never take the contract.
# With K independent contracts per round, a per-firm budget of b bits is split
# across contracts; profit is additive, so the best split is found by search.
#
# The solver itself now lives in testbed/solver (N firms, exact DP over
# thresholds, pi_0 and pi_comp as well); this script prints the plan's tables.
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from testbed.solver import Market, benchmarks, frontier, full_info_value, per_contract_frontier, r90  # noqa: E402

m = Market(n_firms=2, cost_low=1, cost_high=12, reserve=10)
full = full_info_value(m)
per_k = per_contract_frontier(m)
p0 = per_k[0]

print("One contract per round:")
for k in range(0, 4):
    print(f"  k={k} bits: share of full {per_k[k]/full:.1%}, "
          f"info-dependent share {(per_k[k]-p0)/(full-p0):.1%}")

for K in (1, 2, 4):
    print(f"\nK={K} contracts per round (budget = bits per firm per round):")
    fr = frontier(m, K, max_bits=8)
    for budget in range(0, 9):
        print(f"  {budget} bits: info-dependent share {(fr[budget][0] - K*p0)/(K*(full-p0)):.1%}")

bm = benchmarks(2, 4, 1, 12, 10)
print(f"\nK=4, N=2 benchmarks (per firm per round): pi_comp {bm['pi_comp']:.3f}, "
      f"pi_0 {bm['pi_0']:.3f} ({bm['pi_0_scheme']['name']} {bm['pi_0_scheme']['params']}), "
      f"pi*(0) {bm['pi_star'][0]:.3f}, pi_full {bm['pi_full']:.3f}; R90 = {r90(bm):.0f} bits")
