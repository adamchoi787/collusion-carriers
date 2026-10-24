"""Observation.framing: plain facts from the config, never prompt text.

The keys match what the LLM agent renders (testbed/agents/prompts FRAMING_KEYS). All
values are strings; a key is absent when it does not apply.
    permission         "none" | "generic" | "forbid" | "named:<ch>,<ch>"   (what the firm is told)
    private_message    "true"  (told, or a real channel)
    free_chat          "true"
    identity           "same" | "different"  (what the firm is told about its rival's model)
    role_told          "competitor" | "auditor" | "maybe_auditor"  (targets only, Study 4)
    role_subject       "<firm>"  (which firm the role claim is about)
    announced_watched  "<medium>,..."  (from monitoring.start_round on)
    fine               "<amount>"  (with announced_watched, when the fine is non-zero)
    swap_announced     "<firm>"  (from the swap round on: that firm is now run by a new agent;
                                  shown to its rivals only)

Game parameters (n_firms, reserve, symbols, ...) go in Observation.rules instead. Nothing here
says which media are actually delivered: that is what agents must not be told.
"""
from __future__ import annotations

from ..types import Config
from .config import private_message_available


def framing(config: Config, firm: int, round: int) -> dict[str, str]:
    f: dict[str, str] = {}
    p = config.permission
    f["permission"] = "named:" + ",".join(p.media) if p.kind == "named" else p.kind
    if private_message_available(config):
        f["private_message"] = "true"
    if config.free_chat:
        f["free_chat"] = "true"
    ident = config.identity
    if ident.told is not None:
        f["identity"] = ident.told
    role_firm = config.n_firms - 1
    if config.role is not None and firm != role_firm:
        f["role_told"] = config.role.told
        f["role_subject"] = str(role_firm)
    mon = config.monitoring
    if mon.announced and round >= mon.start_round:
        f["announced_watched"] = ",".join(mon.announced)
        if mon.fine:
            f["fine"] = f"{mon.fine:g}"
    swap = ident.swap
    if swap is not None and swap.announced and round >= swap.at_round and firm != swap.firm:
        f["swap_announced"] = str(swap.firm)
    return f
