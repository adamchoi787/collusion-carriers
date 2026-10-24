"""The vllm provider against a fake OpenAI-compatible endpoint (a local HTTP
server), per-call seeds, the $0 / GPU-time accounting, and serve_vllm's
settings. Nothing here talks to Modal or downloads weights."""
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import testbed.agents.llm as llm
from testbed.agents.budget import Caps, LocalLedger, Prices
from testbed.agents.llm import LLMAgent, call_seed
from testbed.agents.providers import make_provider
from testbed.agents.providers.openai_compat import OpenAICompatProvider
from testbed.agents.spend import report
from testbed.engine import read_log, run
from testbed.studies import study1
from testbed.types import MEDIA, AgentSpec, Observation

QWEN = "Qwen/Qwen3.8-27B-FP8"
SAMPLING = {"temperature", "top_p", "top_k", "min_p", "presence_penalty", "frequency_penalty"}


def reply_for(body: dict) -> str:
    """A valid reply for the phase, chosen from the seed, so equal seeds give equal games."""
    last = body["messages"][-1]["content"]
    s = body.get("seed", 0)
    if "Bidding stage" in last:
        return json.dumps({"bids": [8 + (s >> i) % 3 for i in range(4)]})
    if "Chat stage" in last:
        return '{"chat": ""}'
    if "Question:" in last:
        return '{"answer": "no"}'
    return json.dumps({m: (s >> (2 * i)) % 4 for i, m in enumerate(MEDIA)})


class FakeVLLM:
    """Minimal /v1/models and /v1/chat/completions. `fail_first` requests get 503."""

    def __init__(self, key="test-key", fail_first=0):
        self.key, self.fail_first, self.requests = key, fail_first, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorised(self):
                if self.headers.get("Authorization") != f"Bearer {fake.key}":
                    self._send(401, {"error": {"message": "unauthorised"}})
                    return False
                return True

            def do_GET(self):
                if self._authorised():
                    self._send(200, {"object": "list", "data": [{"id": QWEN, "object": "model"}]})

            def do_POST(self):
                if not self._authorised():
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                if len(fake.requests) <= fake.fail_first:
                    return self._send(503, {"error": {"message": "loading"}})
                n = sum(len(m["content"]) for m in body["messages"]) // 4
                self._send(200, {
                    "id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": reply_for(body)}}],
                    "usage": {"prompt_tokens": n, "completion_tokens": 12, "total_tokens": n + 12,
                              "prompt_tokens_details": {"cached_tokens": n // 2}}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def endpoint(monkeypatch, tmp_path):
    fake = FakeVLLM()
    monkeypatch.setenv("VLLM_BASE_URL", fake.url)
    monkeypatch.setenv("VLLM_API_KEY", fake.key)
    led = LocalLedger(tmp_path / "ledger.jsonl", caps=Caps())
    monkeypatch.setattr(llm, "get_ledger", lambda *a, **k: led)
    fake.ledger = led
    yield fake
    fake.close()


def spec(**params):
    return AgentSpec(kind="llm", provider="vllm", model=QWEN, reasoning="off",
                     params={"rate_limit_wait_s": 0.01, **params})


def obs(phase="prebid", r=1, firm=0, **kw):
    return Observation(firm=firm, round=r, phase=phase, costs=[3, 9, 12, 5], z=1,
                       defaults={m: 1 for m in MEDIA}, framing={}, **kw)


def test_request_shape_seed_and_no_sampling_params(endpoint):
    agent = LLMAgent(spec(), run_seed=7)
    a = agent.act(obs())
    body = endpoint.requests[-1]
    assert body["model"] == QWEN and not SAMPLING & set(body)
    assert body["seed"] == call_seed(7, 1, 0, "prebid") == a.usage["seed"]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["response_format"]["type"] == "json_schema" and body["max_tokens"] > 0
    assert a.prebid and not a.usage["fallback"] and a.usage["usd"] == 0 and a.usage["cached"] > 0


def test_prompt_only_mode_sends_no_schema(endpoint):
    LLMAgent(spec(structured=False), run_seed=0).act(obs())
    assert "response_format" not in endpoint.requests[-1]


def test_reasoning_mapping_and_hosted_providers_never_get_a_seed():
    from testbed.agents.providers.openai_compat import reasoning_kwargs

    assert reasoning_kwargs("vllm", None) == {}
    assert reasoning_kwargs("vllm", "on") == {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}
    with pytest.raises(ValueError):
        reasoning_kwargs("vllm", "high")

    sent = {}

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent.update(kw)
                    raise RuntimeError("stop")

    for name in ("deepseek", "openai", "moonshot", "minimax"):
        sent.clear()
        p = OpenAICompatProvider(name, client=Client())
        assert not p.accepts_seed
        with pytest.raises(RuntimeError):
            p.complete(model="m", system="s", messages=[], json_schema=None, max_tokens=5, reasoning=None, seed=3)
        assert "seed" not in sent and "seed" not in sent.get("extra_body", {})


def test_call_seed_is_stable_and_distinct():
    assert call_seed(0, 1, 0, "prebid") == call_seed(0, 1, 0, "prebid")
    assert 0 <= call_seed(5, 100, 2, "bid", "arrangement", 1) < 2 ** 31
    seeds = {call_seed(s, r, f, ph, None, a) for s in range(2) for r in range(1, 6) for f in range(3)
             for ph in ("chat", "prebid", "bid", "probe") for a in range(2)}
    assert len(seeds) == 2 * 5 * 3 * 4 * 2
    assert call_seed(0, 3, 1, "probe", "a") != call_seed(0, 3, 1, "probe", "b")
    assert call_seed(0, 1, 0, "prebid") == 1835727361   # golden: same seeds in every process


def test_games_through_the_engine_are_reproducible(endpoint, tmp_path):
    """Same card and seed -> the same per-call seeds -> the same game on a seeded server."""
    def play(seed, name):
        cfg = study1.card("s1-free-chat", seed=seed, rounds=3)
        cfg.agents = [spec()] * 2
        from testbed.engine import LocalStorage

        res = run(cfg, storage=LocalStorage(str(tmp_path / name)))
        return [(r["round"], r["firm"], r["prebid"], r["bids"], r["usage"]["bid"]["seed"])
                for r in res.records], res

    a, res = play(4, "a")
    b, _ = play(4, "b")
    c, _ = play(5, "c")
    assert a == b and a != c
    log = read_log(str(tmp_path / "a" / res.config.card_id / "4.jsonl"))
    usage = [r["usage"] for r in log if r["type"] == "round"]
    assert all("seed" in u[ph] for u in usage for ph in ("chat", "prebid", "bid"))
    p = endpoint.ledger.summary()["providers"]["vllm"]
    assert p["settled_usd"] == 0 and p["calls"] == len(endpoint.requests) >= 3 * 3 * 2 * 3 and p["reserved"] == {}


def test_cold_endpoint_is_waited_out_not_fallen_back(endpoint):
    """The SDK retries a 503 three times itself; the agent then keeps waiting
    (a self-hosted endpoint may be booting) instead of falling back."""
    endpoint.fail_first = 5
    a = LLMAgent(spec(), run_seed=0).act(obs())
    assert not a.usage["fallback"] and a.usage["rate_limited"] == 1 and len(endpoint.requests) == 6


def test_wait_ready(endpoint, monkeypatch):
    from testbed.serve_vllm import wait_ready

    assert wait_ready(QWEN) >= 0
    monkeypatch.setenv("VLLM_API_KEY", "wrong")
    with pytest.raises(PermissionError):
        wait_ready(QWEN)
    monkeypatch.setenv("VLLM_API_KEY", endpoint.key)
    with pytest.raises(TimeoutError):
        wait_ready("other/model", timeout_s=0)


def test_vllm_needs_no_cap_but_one_set_is_enforced(monkeypatch):
    assert math.isinf(Caps().for_provider("vllm")) and Caps().for_provider("deepseek") == 0
    monkeypatch.setenv("BUDGET_USD_VLLM", "0.5")
    assert Caps.from_env().for_provider("vllm") == 0.5
    monkeypatch.setenv("BUDGET_USD_VLLM", "")
    assert math.isinf(Caps.from_env().for_provider("vllm"))


def test_gpu_time_is_modal_compute(tmp_path):
    prices = Prices.load()
    assert prices.gpu_cost(3600, "L40S") == pytest.approx(1.9512)
    assert prices.gpu_cost(10, "A100-80GB", cpu=2, memory_gib=16) > prices.gpu_cost(10, "A100-80GB")
    led = LocalLedger(tmp_path / "l.jsonl", caps=Caps())
    led.record_compute("gpu:qwen", 60, prices.gpu_cost(60, "L40S"), gpu="L40S")
    led.record_compute("gpu:qwen", 60, prices.gpu_cost(60, "L40S"), gpu="L40S")
    led.record_compute("s1/0", 30, 0.001)
    c = led.summary()["compute"]
    assert c["jobs"] == 1 and c["gpu"]["L40S"]["seconds"] == 120 and c["usd"] == pytest.approx(
        2 * prices.gpu_cost(60, "L40S") + 0.001)
    text = report(led.summary(), led.caps)
    assert "gpu L40S" in text and "0.03 GPU-h" in text
    assert [ln for ln in text.splitlines() if ln.startswith("vllm")][0].split()[2] == "none"


def test_serve_settings():
    import testbed.serve_vllm as sv

    prices = Prices.load()
    assert {m.repo for m in sv.MODELS.values()} == set(prices.provider("vllm")["models"])
    assert len({m.repo.split("/")[0] for m in sv.MODELS.values()}) == 2      # two different labs
    for m in sv.MODELS.values():
        prices.gpu_cost(1, m.gpu)                                          # every GPU is priced
        cmd = sv.serve_command(m)
        assert "--enable-prefix-caching" in cmd and cmd[cmd.index("--served-model-name") + 1] == m.repo
        assert cmd[cmd.index("--generation-config") + 1] == "auto"
        assert not any(f.lstrip("-").replace("-", "_") in SAMPLING for f in cmd)
        assert "--api-key" not in cmd          # the key comes from the environment, never argv
    assert 0 < sv.SCALEDOWN_S <= 600 and sv.MAX_CONTAINERS == 1
    with pytest.raises(ValueError):
        sv.endpoint_url("meta/unknown")


def test_make_provider_uses_the_per_agent_url(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    p = make_provider("vllm", model=QWEN, url="http://127.0.0.1:9/v1")
    assert str(p.client.base_url).startswith("http://127.0.0.1:9/v1") and p.accepts_seed
