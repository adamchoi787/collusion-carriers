"""Build agents from AgentSpecs.

A factory is `factory(spec: AgentSpec, firm: int, config: Config) -> Agent`, keyed by
`spec.kind`. "scripted" and "llm" (testbed.agents.llm.LLMAgent(spec), imported lazily)
are built in. For any other kind the registry imports `testbed.agents.<kind>` and
uses its `make_agent(spec, firm, config)`, unless a factory was registered with
`register_agent_kind`.
"""
from __future__ import annotations

import importlib
from typing import Callable, Protocol

from ..types import Action, AgentSpec, Config, Observation


class Agent(Protocol):
    def act(self, obs: Observation) -> Action: ...
    def snapshot(self) -> dict: ...
    def restore(self, state: dict) -> None: ...


AgentFactory = Callable[[AgentSpec, int, Config], Agent]
_REGISTRY: dict[str, AgentFactory] = {}


def register_agent_kind(kind: str, factory: AgentFactory) -> None:
    _REGISTRY[kind] = factory


def make_agent(spec: AgentSpec, firm: int, config: Config) -> Agent:
    factory = _REGISTRY.get(spec.kind)
    if factory is None:
        module = importlib.import_module(f"testbed.agents.{spec.kind}")
        factory = module.make_agent
    return factory(spec, firm, config)


def spec_label(spec: AgentSpec | None) -> str:
    if spec is None:
        return "object"
    if spec.kind == "scripted":
        return f"scripted:{spec.policy}"
    return f"{spec.kind}:{spec.provider}/{spec.model}"


def parse_agent_arg(arg: str) -> AgentSpec:
    """`scripted:honest`, `scripted:kbit_colluder:medium=val,k=2`, `llm:anthropic/claude-opus-5-5`."""
    kind, _, rest = arg.partition(":")
    name, _, params_s = rest.partition(":")
    params = {}
    for item in filter(None, params_s.split(",")):
        k, _, v = item.partition("=")
        params[k] = int(v) if v.lstrip("-").isdigit() else (float(v) if _is_float(v) else v)
    if kind == "scripted":
        return AgentSpec(kind="scripted", policy=name, params=params)
    provider, _, model = name.partition("/")
    reasoning = params.pop("reasoning", None)
    return AgentSpec(kind=kind, provider=provider or None, model=model or None,
                     reasoning=None if reasoning is None else str(reasoning), params=params)


def _is_float(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _scripted(spec: AgentSpec, firm: int, config: Config) -> Agent:
    from ..agents.scripted import make_agent as make
    return make(spec, firm, config)


def _llm(spec: AgentSpec, firm: int, config: Config) -> Agent:
    module = importlib.import_module("testbed.agents.llm")
    if hasattr(module, "make_agent"):
        return module.make_agent(spec, firm, config)
    return module.LLMAgent(spec)


register_agent_kind("scripted", _scripted)
register_agent_kind("llm", _llm)
