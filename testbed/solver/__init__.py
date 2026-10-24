"""Solver benchmarks: pi_comp, pi_0, pi*(k), pi_full for N firms and K contracts.

See README.md in this directory for the model, the searched families and the
known caveats.
"""
from .benchmarks import benchmarks, format_frontier, frontier_table, info_share, r90
from .collusive import Market, best_partition, frontier, full_info_value, per_contract_frontier
from .competitive import analytic_equilibrium, exploitability, fictitious_play
from .zero_bit import best_zero_bit

__all__ = [
    "benchmarks", "frontier_table", "format_frontier", "r90", "info_share",
    "Market", "best_partition", "frontier", "full_info_value", "per_contract_frontier",
    "analytic_equilibrium", "exploitability", "fictitious_play", "best_zero_bit",
]
