"""Provider adapters behind one interface (see base.Provider)."""
from __future__ import annotations

from .base import Completion, Provider, strip_think

__all__ = ["Completion", "Provider", "make_provider", "strip_think"]


def make_provider(name: str, extra_body: dict | None = None) -> Provider:
    from ..budget import load_env

    load_env()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    from .openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(name, extra_body=extra_body)
