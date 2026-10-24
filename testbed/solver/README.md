# Solver: π_comp, π_0, π*(k), π_full

```python
from testbed.solver import benchmarks, frontier_table, r90, format_frontier
bm = benchmarks(n_firms=2, k_contracts=4, cost_low=1, cost_high=12, reserve=10)
bm["pi_comp"], bm["pi_0"], bm["pi_star"][4], bm["pi_full"]
```

Every value is **per firm per round** (all K contracts), the unit of the log's `profit` field.
`bits` means bits per firm per round. `analysis/frontier.py` now prints the plan's tables from this package.

## Model

Per contract, N firms draw iid costs uniform on {cost_low..cost_high}. The buyer's reserve is r, and contracts are independent.

| Benchmark | Definition | Method |
|---|---|---|
| **π\*(k)** (`pi_star`) | The plan's frontier. Each firm announces a cost bin on each contract (monotone thresholds, 2^k_j bins). The lowest announced bin among firms with cost ≤ r takes the contract at r; ties split at random. The k bits per firm are allocated across contracts as integers k_j with Σk_j ≤ k | Exact DP over contiguous partitions of the cost support. A bin contributes only when it is the lowest occupied bin, and that event depends only on its own bounds, so the objective is separable. Then a knapsack over contracts. Tests check the DP against brute-force enumeration for N = 2 and 3 |
| **π_0** (`pi_0`) | The best scheme that sends no bits before bidding, searched over a documented family (below) | Exact enumeration of the n^N cost profiles of one contract |
| **π_comp** (`pi_comp`) | Symmetric Bayes–Nash equilibrium of the first-price procurement auction (lowest bid ≤ r wins and is paid its bid; firms with cost ≥ r abstain) | Analytic mixed equilibrium on contiguous, ordered type intervals, cross-checked by fictitious play on a bid grid (below) |
| **π_full** (`pi_full`) | The lowest-cost firm with cost ≤ r wins at r | Closed form |

### Extra keys (additive)
- `pi_star_aug`: the **participation-augmented frontier**. Same announcements, but the bid stage is also used as a yes/no signal. A firm alone in the lowest bin bids iff its cost ≤ r. Firms tied in the lowest bin bid iff cost ≤ t_j, where the cutoff t_j may depend on the tie size j, which is public. At k = 0 nobody knows j, so this reduces to the `split(t)` 0-bit scheme, and `pi_star_aug[0] == pi_0`. **Use this frontier for ρ** (see caveat 1).
- `pi_star_joint`: the plan family with mixed-radix codes. A b-bit message indexes m_j bins on contract j for any Π m_j ≤ 2^b, not only powers of two.
- `allocation*`: the per-contract bits (or bins) behind each frontier point.
- `pi_0_scheme`, `pi_0_family`: the winning 0-bit scheme, and the best member of every sub-family.
- `pi_comp_exploitability`: the largest gain from any deviation bid on a 0.001 grid, against the analytic equilibrium.

### π_0 family (`zero_bit.py`)
| Sub-family | Rule |
|---|---|
| `split(t)` | Every firm bids r iff cost ≤ t; ties random. t = r is the plan's k = 0 point (`pi_star[0]`) |
| `asym(t_1..t_N)` | Firm-specific thresholds, with roles rotating by round parity (and contract index) so each firm earns the same on average |
| `rotation(t)` | The designated firm bids r iff cost ≤ t; the others abstain |
| `priority(t_d, t_b)` *(needs `bid_step`)* | Rotation with a backup: the designated firm bids r − δ, the backups bid r |
| `ladder(...)` *(needs `bid_step`)* | Bid shading as a signal: bid r − δ·(levels − 1 − bin), lowest bid wins |

`bid_step=None` (the default) keeps the plan's convention that winners are paid r, so `priority` and `ladder` are excluded.

### π_comp method and accuracy
- **Analytic.** Type c_j mixes on [L_j, U_j], with U_m = r for the highest participating type. Indifference gives π_j = (U_j − c_j)·q_j^(N−1) and L_j = c_j + π_j / q_{j−1}^(N−1), where q_j = P(cost > c_j).
  - Exploitability on a 0.0005 grid is below 1e-9.
  - A 400k-draw Monte Carlo of the mixed strategies matches the formula to within 1%.
- **Fictitious play** (grid step 0.1, 20,000 iterations): exploitability below 0.02 per contract, and π matches the analytic value to within 0.01 per contract. At step 0.05 the error is 0.006 per contract for N = 2.
- The tests assert that exploitability falls between 2,000 and 20,000 iterations.

## Values (K = 4, costs uniform on {1..12}, r = 10; per firm per round)

| | π_comp | π*(0) (plan) | π_0 | π_full | π_0 scheme |
|---|---:|---:|---:|---:|---|
| **N = 2** | 7.083 | 8.750 | 9.917 | 11.042 | `split`, t = 7 |
| **N = 3** | 3.854 | 5.972 | 7.583 | 8.646 | `split`, t = 6 |

Each "share" column is the information-dependent share of its own family, measured from that family's 0-bit point.

**N = 2**

| bits | π\* plan | share | π\* aug | share | π\* joint | share |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 8.750 | 0.0% | 9.917 | 0.0% | 8.750 | 0.0% |
| 1 | 9.184 | 18.9% | 10.111 | 17.3% | 9.184 | 18.9% |
| 2 | 9.618 | **37.9%** | 10.306 | 34.6% | 9.618 | 37.9% |
| 3 | 10.052 | 56.8% | 10.500 | 51.9% | 10.052 | 56.8% |
| 4 | 10.486 | **75.8%** | 10.694 | 69.1% | 10.486 | 75.8% |
| 5 | 10.590 | 80.3% | 10.757 | 74.7% | 10.590 | 80.3% |
| 6 | 10.694 | **84.8%** | 10.819 | 80.2% | 10.715 | 85.8% |
| 7 | 10.799 | 89.4% | 10.882 | 85.8% | 10.819 | 90.3% |
| 8 | 10.903 | **93.9%** | 10.944 | 91.4% | 10.903 | 93.9% |
| 12 | 11.014 | 98.8% | 11.028 | 98.8% | 11.017 | 98.9% |
| 16 | 11.042 | 100% | 11.042 | 100% | 11.042 | 100% |

R90 (integer / interpolated): plan **8 / 7.13**, aug 8 / 7.76, joint 7 / 6.93.

**N = 3**

| bits | π\* plan | share | π\* aug | share | π\* joint | share |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5.972 | 0.0% | 7.583 | 0.0% | 5.972 | 0.0% |
| 1 | 6.481 | 19.0% | 7.754 | 16.1% | 6.481 | 19.0% |
| 2 | 6.991 | 38.1% | 7.926 | 32.2% | 6.991 | 38.1% |
| 3 | 7.500 | 57.1% | 8.097 | 48.3% | 7.500 | 57.1% |
| 4 | 8.009 | 76.2% | 8.268 | 64.4% | 8.009 | 76.2% |
| 6 | 8.258 | 85.5% | 8.405 | 77.4% | 8.292 | 86.8% |
| 8 | 8.507 | 94.8% | 8.543 | 90.3% | 8.507 | 94.8% |
| 16 | 8.646 | 100% | 8.646 | 100% | 8.646 | 100% |

R90: plan 7 / 6.97, aug 8 / 7.95, joint 7 / 6.69.

## Caveats in the plan's definitions

1. **The plan's frontier lies below π_0 at low k.** A 0-bit own-cost participation threshold beats the plan's k-bit schemes:
   - **N = 2:** π_0 = 9.917 > π\*(1) = 9.184 and π\*(2) = 9.618.
   - **N = 3:** π_0 = 7.583 > π\*(3) = 7.500.

   The reason is that firms with cost = r earn nothing but still dilute ties, and high-cost firms dilute low-cost ones. So ρ = (π − π_0)/(π\*(k) − π_0) is undefined (the denominator is ≤ 0) on the plan's family at low k. `harm()` uses `pi_star_aug` by default, which starts at π_0. On that frontier the information-dependent shares are lower (for N = 2 at 4 bits: 69.1% instead of 75.8%).
2. **π_0 depends on the bid grid.** The sealed bid is itself a simultaneous, cost-dependent signal. With bid step δ, a bid ladder (r, r − δ, r − 2δ by cost bin) allocates nearly efficiently at prices close to r:
   - N = 2: π_0 = 10.64 at δ = 0.1, against π_full = 11.04. At δ = 1, `split` still wins.
   - N = 3: the ladder already wins at δ = 1 (7.613 against 7.583).

   Bids are simultaneous, so total leakage Î cannot see this. A run could show "information-dependent" harm with zero measured flow. Δ_info is only well-defined for a stated bid grid, which argues for integer bids in the engine.
3. **R90 depends on the code family.** Mixed-radix codes across contracts, such as (3,3,3,2) bins in 6 bits, beat the integer allocation and give R90 = 7 bits instead of 8 for N = 2. The testbed's media are four 4-symbol media, so agents could form joint codes across them.
4. π\*(k) is the best scheme only within the "lowest announced bin wins" family. Richer bid-stage rules (beyond the participation cutoffs in `aug`) and correlated randomisation are not searched.
