"""Intervention hooks.

A plugin subclasses `Plugin` and overrides any hooks it needs; the engine calls
every plugin's hook in list order. Later studies (monitoring and fines, swaps,
the third participant) are plugins, so the core loop never changes.

Order within a round r:

    on_round_start(engine, r)
    [chat]    transform_observation(engine, obs)  -> agents act
              transform_messages(engine, r, deliveries)
    [prebid]  transform_observation(engine, obs)  -> agents act
              on_prebids(engine, r, prebids)
              transform_shown(engine, r, shown)
    [bid]     transform_observation(engine, obs)  -> agents act
              on_bids(engine, r, bids)            -> bids
    reveal    (auction resolved)
    [probe]   transform_observation(engine, obs)  -> agents answer
    on_round_end(engine, r, records)              (engine.add_fine / add_flag here)

Plugin state must survive checkpoints: return JSON-serialisable data from
`state_dict` and restore it in `load_state_dict`. State is matched by `name`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..types import Observation

if TYPE_CHECKING:
    from .game import Engine

# shown[observer][sender][medium] = value | "unavailable"   (absent = hidden)
Shown = dict[int, dict[int, dict[str, "int | str"]]]


class Plugin:
    name: str = "plugin"

    def on_run_start(self, engine: "Engine") -> None:
        """Called once, before the first round run by this engine (also after a branch)."""

    def on_round_start(self, engine: "Engine", round: int) -> None:
        """Costs and z for `round` are already drawn (engine.costs, engine.z)."""

    def transform_observation(self, engine: "Engine", obs: Observation) -> Observation:
        """Edit what one firm sees (framing, rivals_prebid, messages, history) before it acts."""
        return obs

    def transform_messages(self, engine: "Engine", round: int, deliveries: list[dict]) -> list[dict]:
        """deliveries: [{"to": firm, "from": firm, "channel": "chat"|"private_message", "text": ...}],
        after decoys are applied. Return the list actually delivered."""
        return deliveries

    def on_prebids(self, engine: "Engine", round: int, prebids: list[dict[str, int]]) -> None:
        """Actual (validated) pre-bid symbols per firm."""

    def transform_shown(self, engine: "Engine", round: int, shown: Shown) -> Shown:
        """What each observer sees of each rival's pre-bid, after visibility and decoys."""
        return shown

    def on_bids(self, engine: "Engine", round: int, bids: list[list[float | None]]) -> list[list[float | None]]:
        """Validated bids per firm per contract; return (possibly edited) bids, e.g. to exclude a firm."""
        return bids

    def on_round_end(self, engine: "Engine", round: int, records: list[dict]) -> None:
        """records[firm] is the log record about to be written. Use engine.add_fine(firm, amount)
        and engine.add_flag(firm, flag) to fine or flag firms for this round."""

    def state_dict(self) -> dict:
        return {}

    def load_state_dict(self, state: dict) -> None:
        pass


class SwapPlugin(Plugin):
    """Applies `config.identity.swap` at its round (Study 3, Part B).

    actual == "none" is a sham: nothing changes (the announcement, if any, is framing).
    "same_model" builds a fresh agent from the replacement spec, else from the firm's own spec;
    "other_provider" needs `replacement`. Unless `wipe_memory`, the new agent is restored from
    the old agent's snapshot. The firm index, the rival's displayed identity, never changes.
    """
    name = "swap"

    def on_round_start(self, engine: "Engine", round: int) -> None:
        swap = engine.config.identity.swap
        if swap is None or swap.actual == "none" or round != swap.at_round:
            return
        spec = swap.replacement or engine.agent_specs[swap.firm]
        if spec is None:
            raise ValueError("swap needs a replacement AgentSpec (the firm's agent was passed as an object)")
        engine.swap_agent(swap.firm, engine.make_agent(spec, swap.firm), wipe_memory=swap.wipe_memory, spec=spec)
