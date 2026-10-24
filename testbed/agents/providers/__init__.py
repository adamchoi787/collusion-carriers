"""Provider adapters behind one interface (see base.Provider)."""
from __future__ import annotations

from .base import Completion, Provider, strip_think

__all__ = ["Completion", "Provider", "make_provider", "strip_think"]


def make_provider(name: str, extra_body: dict | None = None, model: str | None = None,
                  url: str | None = None) -> Provider:
    """`model` and `url` matter only for vllm, whose endpoint is per model."""
    from ..budget import load_env

    load_env()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    from .openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(name, extra_body=extra_body, model=model, url=url)
