"""All engine randomness, keyed so that it never depends on agent behaviour.

Costs and z for (seed, round, firm) come from default_rng([seed, round, firm]):
the same in every card (common random numbers). Scramble and tie-break draws use
their own keyed streams, so they never disturb costs. Tags are odd constants and
the last entry is never 0, because SeedSequence treats trailing zeros as absent.
"""
from __future__ import annotations

import numpy as np

_SCRAMBLE = 2_000_003
_SCRAMBLE_MSG = 2_000_033
_TIE = 1_000_003


def draw(seed: int, round: int, firm: int, k: int, cost_low: int, cost_high: int,
         z_levels: int) -> tuple[list[int], int]:
    g = np.random.default_rng([seed, round, firm])
    costs = g.integers(cost_low, cost_high + 1, size=k)
    z = g.integers(0, z_levels)
    return [int(c) for c in costs], int(z)


def scramble_round(seed: int, round: int, firm: int, medium_index: int, n_earlier: int) -> int:
    """A uniformly random earlier round, 1..n_earlier."""
    g = np.random.default_rng([seed, round, firm, _SCRAMBLE, medium_index + 1])
    return 1 + int(g.integers(0, n_earlier))


def scramble_message(seed: int, round: int, sender: int, to: int, n_earlier: int) -> int:
    g = np.random.default_rng([seed, round, sender, _SCRAMBLE_MSG, to + 1])
    return int(g.integers(0, n_earlier))


def tie_break(seed: int, round: int, contract: int, n_tied: int) -> int:
    g = np.random.default_rng([seed, round, _TIE, contract + 1])
    return int(g.integers(0, n_tied))
