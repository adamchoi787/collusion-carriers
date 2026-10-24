"""Provider adapters build requests without sampling parameters, map the
reasoning setting as documented, and normalise usage. Fake SDK clients only."""
from types import SimpleNamespace as NS

import pytest

from testbed.agents.providers.anthropic_provider import AnthropicProvider
from testbed.agents.providers.openai_compat import OpenAICompatProvider

SAMPLING = {"temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "seed"}
SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"],
          "additionalProperties": False}
MSGS = [{"role": "user", "content": "go"}]


class FakeAnthropic:
    def __init__(self):
        self.kwargs = None
        self.messages = self

    def create(self, **kw):
        self.kwargs = kw
        usage = NS(input_tokens=10, cache_read_input_tokens=100, cache_creation_input_tokens=5, output_tokens=7)
        return NS(usage=usage, content=[NS(type="thinking", thinking=""), NS(type="text", text='{"a": 1}')],
                  stop_reason="end_turn", model=kw["model"])


class FakeOpenAI:
    def __init__(self):
        self.kwargs = None
        self.chat = NS(completions=self)

    def create(self, **kw):
        self.kwargs = kw
        usage = NS(prompt_tokens=50, completion_tokens=9, prompt_tokens_details=NS(cached_tokens=32))
        msg = NS(content='<think>hmm</think>{"a": 1}')
        return NS(usage=usage, choices=[NS(message=msg, finish_reason="stop")], model=kw["model"])


@pytest.mark.parametrize("reasoning", [None, "low", "medium", "disabled:low"])
def test_anthropic_sends_no_sampling_params(reasoning):
    client = FakeAnthropic()
    comp = AnthropicProvider(client=client).complete(
        model="claude-haiku-5-5", system="sys", messages=MSGS, json_schema=SCHEMA, max_tokens=512,
        reasoning=reasoning)
    kw = client.kwargs
    assert not SAMPLING & set(kw), kw
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    if reasoning and reasoning != "disabled:low":
        assert kw["output_config"]["effort"] == reasoning and "thinking" not in kw
    if reasoning == "disabled:low":
        assert kw["thinking"] == {"type": "disabled"} and kw["output_config"]["effort"] == "low"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert comp.text == '{"a": 1}'
    assert comp.usage == {"input": 115, "cached": 100, "cache_write": 5, "output": 7}


def test_anthropic_rejects_unknown_reasoning():
    with pytest.raises(ValueError):
        AnthropicProvider(client=FakeAnthropic()).complete(
            model="m", system="s", messages=MSGS, json_schema=None, max_tokens=1, reasoning="temperature=0")


@pytest.mark.parametrize("provider", ["openai", "deepseek", "moonshot", "minimax"])
@pytest.mark.parametrize("reasoning", [None, "low", "off"])
def test_openai_compatible_sends_no_sampling_params(provider, reasoning):
    if provider == "openai" and reasoning == "off":
        reasoning = "minimal"
    client = FakeOpenAI()
    comp = OpenAICompatProvider(provider, client=client).complete(
        model="m", system="sys", messages=MSGS, json_schema=SCHEMA, max_tokens=256, reasoning=reasoning)
    kw = client.kwargs
    assert not SAMPLING & set(kw) and not SAMPLING & set(kw.get("extra_body", {})), kw
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert ("max_completion_tokens" if provider == "openai" else "max_tokens") in kw
    assert comp.text == '{"a": 1}' and comp.usage == {"input": 50, "cached": 32, "output": 9}


def test_reasoning_mapping():
    from testbed.agents.providers.openai_compat import reasoning_kwargs as rk

    assert rk("openai", "low") == {"reasoning_effort": "low"}
    assert rk("deepseek", "off") == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert rk("deepseek", "low") == {"extra_body": {"thinking": {"type": "enabled"}}, "reasoning_effort": "low"}
    assert rk("moonshot", "off") == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert rk("minimax", "disabled")["extra_body"]["thinking"] == {"type": "disabled"}
    assert rk("minimax", None) == {"extra_body": {"reasoning_split": True}}


def test_base_url_override(monkeypatch):
    from testbed.agents.providers.openai_compat import base_url

    monkeypatch.delenv("MOONSHOT_BASE_URL", raising=False)
    assert base_url("moonshot") == "https://api.moonshot.cn/v1"
    monkeypatch.setenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1")
    assert base_url("moonshot") == "https://api.moonshot.ai/v1"
