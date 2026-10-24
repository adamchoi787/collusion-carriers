"""Config <-> plain dict <-> YAML, plus facts derived from a Config.

`config_from_dict` rebuilds the nested dataclasses from type hints and rejects
unknown keys, so a typo in a YAML card fails loudly instead of being ignored.
"""
from __future__ import annotations

import dataclasses
import types as _pytypes
import typing
from typing import Any, Literal, Union

import yaml

from .. import types as T
from ..types import MEDIA, Config

PRIVATE_MESSAGE = "private_message"
CHANNELS = (*MEDIA, PRIVATE_MESSAGE)

# What an observer is actually shown for a channel, after decoys are applied.
#   delivered: the real value        scrambled: the sender's value from a random earlier round
#   error:     the string "unavailable"     hidden: nothing (the field is absent)
Shown = Literal["delivered", "scrambled", "error", "hidden"]


# ---- dict / YAML -----------------------------------------------------------

def config_to_dict(config: Config) -> dict:
    return _plain(dataclasses.asdict(config))


def _plain(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def config_from_dict(d: dict) -> Config:
    return _build(Config, d)


def _hints(cls) -> dict:
    return typing.get_type_hints(cls, vars(T))


def _build(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    if dataclasses.is_dataclass(tp):
        if not isinstance(value, dict):
            raise TypeError(f"{tp.__name__}: expected a mapping, got {value!r}")
        hints = _hints(tp)
        names = {f.name for f in dataclasses.fields(tp)}
        unknown = set(value) - names
        if unknown:
            raise ValueError(f"{tp.__name__}: unknown field(s) {sorted(unknown)}")
        return tp(**{k: _build(hints[k], v) for k, v in value.items()})
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (Union, _pytypes.UnionType):
        for a in args:
            if a is type(None):
                continue
            if dataclasses.is_dataclass(a):
                return _build(a, value)
        return _build(next(a for a in args if a is not type(None)), value)
    if origin is list:
        return [_build(args[0], v) for v in value]
    if origin is tuple:
        return tuple(value)
    if origin is dict:
        return {k: _build(args[1], v) for k, v in value.items()}
    return value


def config_to_yaml(config: Config) -> str:
    return yaml.safe_dump(config_to_dict(config), sort_keys=False)


def config_from_yaml(text: str) -> Config:
    return config_from_dict(yaml.safe_load(text))


def load_config(path: str) -> Config:
    with open(path) as f:
        return config_from_yaml(f.read())


def save_config(config: Config, path: str) -> None:
    with open(path, "w") as f:
        f.write(config_to_yaml(config))


# ---- derived facts ----------------------------------------------------------

def told_channels(config: Config) -> list[str]:
    """Channels agents are explicitly told they may use (named permission only)."""
    return list(config.permission.media) if config.permission.kind == "named" else []


def effective_visibility(config: Config) -> dict[str, Shown]:
    """What rivals are shown on each channel.

    `delivered` and `scrambled` in `config.visibility` are taken as given. A channel
    that is told (named permission) but not delivered is a decoy and behaves as
    `permission.decoy_mode`. Anything else is hidden.
    """
    told = set(told_channels(config))
    out: dict[str, Shown] = {}
    for ch in CHANNELS:
        v = config.visibility.get(ch, "hidden")
        if v in ("delivered", "scrambled"):
            out[ch] = v
        elif ch in told:
            out[ch] = config.permission.decoy_mode
        else:
            out[ch] = "hidden"
    return out


def private_message_available(config: Config) -> bool:
    return PRIVATE_MESSAGE in told_channels(config) or config.visibility.get(PRIVATE_MESSAGE) == "delivered"


def validate(config: Config) -> None:
    if config.n_firms < 2:
        raise ValueError("n_firms must be >= 2")
    if config.k_contracts < 1 or config.rounds < 1:
        raise ValueError("k_contracts and rounds must be >= 1")
    if not config.cost_low <= config.cost_high:
        raise ValueError("cost_low > cost_high")
    for m in MEDIA:
        if config.symbols.get(m, 0) < 1:
            raise ValueError(f"symbols[{m!r}] must be >= 1")
    for ch, v in config.visibility.items():
        if ch not in CHANNELS:
            raise ValueError(f"visibility: unknown channel {ch!r}")
        if v not in ("delivered", "scrambled", "hidden"):
            raise ValueError(f"visibility[{ch!r}] = {v!r}")
    for ch in config.permission.media:
        if ch not in (*CHANNELS, "chat"):
            raise ValueError(f"permission.media: unknown channel {ch!r}")
    if config.agents and len(config.agents) not in (1, config.n_firms):
        raise ValueError("config.agents must have 1 or n_firms entries")
