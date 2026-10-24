"""One interface for every provider: text in, text plus usage out.

Adapters never set sampling parameters (temperature, top_p, top_k). The
reasoning/effort setting is passed through from AgentSpec.reasoning and each
adapter maps it to its own request field; the agent records it verbatim.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Completion:
    text: str
    # input = all prompt tokens (uncached + cache reads + cache writes);
    # cached = cache-read tokens; output includes any reasoning tokens.
    usage: dict = field(default_factory=lambda: {"input": 0, "cached": 0, "output": 0})
    model: str = ""
    finish: str | None = None


class Provider:
    """Adapters implement complete(). `json_schema` asks for structured output
    where the provider supports it; adapters that only have a JSON mode use
    that, and the rest rely on the prompt (the agent validates either way)."""

    name: str = "base"

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        json_schema: dict | None,
        max_tokens: int,
        reasoning: str | None,
    ) -> Completion:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        raise NotImplementedError


def strip_think(text: str) -> str:
    """Drop <think>...</think> blocks some OpenAI-compatible models inline."""
    while "<think>" in text and "</think>" in text:
        a, b = text.index("<think>"), text.index("</think>") + len("</think>")
        text = text[:a] + text[b:]
    return text.strip()
