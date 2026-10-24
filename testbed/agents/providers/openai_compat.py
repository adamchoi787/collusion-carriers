"""OpenAI and the OpenAI-compatible providers (DeepSeek, Moonshot/Kimi, MiniMax),
all through the official `openai` SDK's Chat Completions endpoint.

No sampling parameters are sent. spec.reasoning maps per provider:

  openai    "low" | "medium" | ... -> reasoning_effort
  deepseek  None -> provider default (thinking on, effort high);
            "off" -> thinking={"type": "disabled"}; "low" | "high" | "max" ->
            thinking={"type": "enabled"} plus reasoning_effort=<value>
  moonshot  None -> provider default (K2.6 thinks by default); "off" ->
            thinking={"type": "disabled"}; "on" -> thinking enabled;
            "low" | "high" | "max" -> reasoning_effort (K3 / K3.1 only)
  minimax   "disabled" -> thinking={"type": "disabled"} (M3; M3.1-Flash 400s);
            otherwise thinking={"type": "adaptive"} plus reasoning_effort=<value>;
            reasoning_split=True always, so thinking never lands in `content`

spec.params["extra_body"] is merged into the request for anything else.
"""
from __future__ import annotations

import os

from .base import Completion, Provider, strip_think

# Default base_url per provider; None = SDK default. <PROVIDER>_BASE_URL in the
# environment overrides it. Moonshot defaults to the China platform
# (platform.moonshot.cn, RMB-funded keys); international keys need
# MOONSHOT_BASE_URL=https://api.moonshot.ai/v1. A key from the other platform
# gets 401 Invalid Authentication.
BASE_URLS = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "moonshot": "https://api.moonshot.cn/v1",
    "minimax": "https://api.minimax.io/v1",
}


def base_url(provider: str) -> str | None:
    return os.environ.get(f"{provider.upper()}_BASE_URL", "").strip() or BASE_URLS[provider]
KEY_ENVS = {p: f"{p.upper()}_API_KEY" for p in BASE_URLS}
# "schema": json_schema response_format; "object": json_object; None: prompt only.
JSON_MODES = {"openai": "schema", "deepseek": "object", "moonshot": "object", "minimax": None}


def reasoning_kwargs(provider: str, reasoning: str | None) -> dict:
    r = (reasoning or "").strip().lower()
    if provider == "openai":
        return {"reasoning_effort": r} if r else {}
    if provider == "deepseek":
        # Thinking is on by default (effort high); None leaves the default.
        if not r:
            return {}
        if r in ("off", "disabled", "none"):
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        body: dict = {"extra_body": {"thinking": {"type": "enabled"}}}
        if r != "on":
            body["reasoning_effort"] = r
        return body
    if provider == "moonshot":
        # K2.6 thinks by default and has no effort setting; K3 / K3.1 take reasoning_effort.
        if not r:
            return {}
        if r in ("off", "disabled", "none"):
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        if r == "on":
            return {"extra_body": {"thinking": {"type": "enabled"}}}
        return {"reasoning_effort": r}
    if provider == "minimax":
        if r == "disabled":
            return {"extra_body": {"thinking": {"type": "disabled"}, "reasoning_split": True}}
        body = {"extra_body": {"reasoning_split": True}}
        if r:
            body["extra_body"]["thinking"] = {"type": "adaptive"}
            body["reasoning_effort"] = r
        return body
    raise ValueError(f"unknown provider {provider!r}")


def _cached_tokens(u) -> int:
    details = getattr(u, "prompt_tokens_details", None)
    n = getattr(details, "cached_tokens", None) if details is not None else None
    if n is None:  # DeepSeek reports hits separately; Moonshot may report top-level
        n = getattr(u, "prompt_cache_hit_tokens", None) or getattr(u, "cached_tokens", None)
    return int(n or 0)


class OpenAICompatProvider(Provider):
    def __init__(self, name: str, client=None, extra_body: dict | None = None):
        if name not in BASE_URLS:
            raise ValueError(f"unknown provider {name!r}")
        self.name = name
        self.extra_body = extra_body or {}
        if client is None:
            import openai

            client = openai.OpenAI(api_key=os.environ.get(KEY_ENVS[name]) or "missing",
                                   base_url=base_url(name), max_retries=3)
        self.client = client

    def complete(self, *, model, system, messages, json_schema, max_tokens, reasoning) -> Completion:
        kw = reasoning_kwargs(self.name, reasoning)
        if self.extra_body:
            kw["extra_body"] = {**kw.get("extra_body", {}), **self.extra_body}
        mode = JSON_MODES[self.name]
        if json_schema is not None and mode == "schema":
            kw["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": "action", "schema": json_schema, "strict": True}}
        elif json_schema is not None and mode == "object":
            kw["response_format"] = {"type": "json_object"}
        # OpenAI counts reasoning in max_completion_tokens; the others take max_tokens.
        kw["max_completion_tokens" if self.name == "openai" else "max_tokens"] = max_tokens
        resp = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            **kw,
        )
        u = resp.usage
        usage = {"input": int(getattr(u, "prompt_tokens", 0) or 0), "cached": _cached_tokens(u),
                 "output": int(getattr(u, "completion_tokens", 0) or 0)}
        choice = resp.choices[0]
        text = strip_think(choice.message.content or "")
        return Completion(text=text, usage=usage, model=resp.model or model, finish=choice.finish_reason)

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self.client.models.list())
