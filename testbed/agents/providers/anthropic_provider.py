"""Anthropic adapter (official `anthropic` SDK).

* No temperature/top_p/top_k: the API rejects them from 2026-10-21.
* spec.reasoning is an effort level ("low" | "medium" | "high" | "xhigh" |
  "max"), sent as output_config.effort with adaptive thinking (the default on
  current models, so `thinking` is omitted). "disabled" sends
  thinking={"type": "disabled"} where the model allows it (Haiku 5.5 at effort
  high or below); prefer a low effort instead. Form "disabled:low" sets both.
* Structured output: output_config.format = json_schema.
* Prompt caching: the system prompt carries a cache breakpoint and top-level
  automatic caching covers the growing, append-only conversation.
"""
from __future__ import annotations

import os

from .base import Completion, Provider

EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def reasoning_params(reasoning: str | None) -> dict:
    out: dict = {}
    if not reasoning:
        return out
    for part in reasoning.split(":"):
        part = part.strip().lower()
        if part in EFFORTS:
            out.setdefault("output_config", {})["effort"] = part
        elif part == "disabled":
            out["thinking"] = {"type": "disabled"}
        elif part == "adaptive":
            out["thinking"] = {"type": "adaptive"}
        elif part:
            raise ValueError(f"anthropic: unknown reasoning setting {part!r}")
    return out


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, client=None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY") or None, max_retries=3)
        self.client = client

    def complete(self, *, model, system, messages, json_schema, max_tokens, reasoning, seed=None) -> Completion:
        # seed is ignored: the Messages API has none, and no sampling parameters are sent.
        kw = reasoning_params(reasoning)
        if json_schema is not None:
            kw.setdefault("output_config", {})["format"] = {"type": "json_schema", "schema": json_schema}
        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            cache_control={"type": "ephemeral"},
            **kw,
        )
        u = resp.usage
        read = getattr(u, "cache_read_input_tokens", 0) or 0
        write = getattr(u, "cache_creation_input_tokens", 0) or 0
        usage = {"input": (u.input_tokens or 0) + read + write, "cached": read,
                 "cache_write": write, "output": u.output_tokens or 0}
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        if resp.stop_reason == "refusal":
            usage["refusal"] = getattr(getattr(resp, "stop_details", None), "category", None) or "unspecified"
        return Completion(text=text, usage=usage, model=resp.model, finish=resp.stop_reason)

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self.client.models.list())
