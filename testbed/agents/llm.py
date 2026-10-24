"""The LLM agent: Observation -> prompt -> provider -> validated Action.

The conversation is append-only, so provider prompt caching works: a system
prompt that never changes after the first observation, then one user turn per
phase (and the assistant reply). Framing changes (e.g. at the round-41
intervention) arrive as an update inside the next user turn, never as an edit.
Only the history rows the agent has not yet seen are appended each round.

Every call goes through the spend guard (budget.py): estimate, reserve,
call, settle. BudgetExceeded propagates to the caller and stops the run.
Invalid output is retried once; then the agent falls back to the cover
default (prebid) or abstains (bid), and says so in Action.usage.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict

from ..types import MEDIA, Action, AgentSpec, Observation
from . import prompts
from .budget import BudgetExceeded, Ledger, Prices, get_ledger
from .providers import Provider, make_provider

CHARS_PER_TOKEN = 2.5    # deliberately low (digit-heavy tables), so estimates run high
DEFAULT_MAX_TOKENS = 4096
SNAPSHOT_VERSION = 1


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def extract_json(text: str) -> dict:
    """First JSON object in the text (tolerates code fences and stray prose)."""
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    raise ValueError("no JSON object found")


def _as_int(v) -> int:
    if isinstance(v, bool):
        raise ValueError("boolean is not an option number")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    raise ValueError(f"{v!r} is not an option number")


def schema_for(obs: Observation, rules: dict, with_pm: bool) -> dict:
    """JSON schema for the phase's reply (strict-mode compatible)."""
    if obs.phase == "prebid":
        props = {m: {"type": "integer", "enum": list(range(rules["symbols"].get(m, 4)))} for m in MEDIA}
        if with_pm:
            props["private_message"] = {"anyOf": [{"type": "null"}, {
                "type": "object", "properties": {"to": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["to", "text"], "additionalProperties": False}]}
    elif obs.phase == "bid":
        props = {"bids": {"type": "array", "items": {"type": ["number", "null"]}}}
    elif obs.phase == "chat":
        props = {"chat": {"type": "string"}}
    else:
        props = {"answer": {"type": "string"}}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def parse_action(text: str, obs: Observation, rules: dict, with_pm: bool) -> Action:
    """Validate a reply; raises ValueError with a short reason the model can read."""
    data = extract_json(text)
    if obs.phase == "prebid":
        pre = {}
        for m in MEDIA:
            if m not in data:
                raise ValueError(f'missing field "{m}"')
            v = _as_int(data[m])
            n = rules["symbols"].get(m, 4)
            if not 0 <= v < n:
                raise ValueError(f'"{m}" must be an option number from 0 to {n - 1}')
            pre[m] = v
        pm = None
        if with_pm and data.get("private_message"):
            raw = data["private_message"]
            if not isinstance(raw, dict) or "to" not in raw or not isinstance(raw.get("text"), str):
                raise ValueError('private_message must be null or {"to": <firm>, "text": "..."}')
            to = _as_int(raw["to"])
            if to == obs.firm:
                raise ValueError("private_message cannot be sent to your own firm")
            pm = {"to": to, "text": raw["text"][:1000]}
        return Action(prebid=pre, private_message=pm)
    if obs.phase == "bid":
        bids = data.get("bids")
        if not isinstance(bids, list) or len(bids) != len(obs.costs):
            raise ValueError(f'"bids" must be a list of {len(obs.costs)} entries')
        out: list[float | None] = []
        for b in bids:
            if b is None:
                out.append(None)
                continue
            if isinstance(b, bool) or not isinstance(b, (int, float)) or not math.isfinite(b) or b < 0:
                raise ValueError("each bid must be a non-negative number or null")
            out.append(float(b))
        return Action(bids=out)
    if obs.phase == "chat":
        chat = data.get("chat")
        if not isinstance(chat, str):
            raise ValueError('"chat" must be a string')
        return Action(chat=chat[:2000] or None)
    answer = data.get("answer")
    if not isinstance(answer, str):
        raise ValueError('"answer" must be a string')
    return Action(answer=answer[:2000])


def fallback_action(obs: Observation) -> tuple[Action, str]:
    if obs.phase == "prebid":
        return Action(prebid={m: obs.defaults[m] for m in MEDIA if m in obs.defaults}), "the operating guideline"
    if obs.phase == "bid":
        return Action(bids=[None] * len(obs.costs)), "no bids"
    if obs.phase == "chat":
        return Action(chat=None), "no message"
    return Action(answer=None), "no answer"


class LLMAgent:
    def __init__(self, spec: AgentSpec, provider: Provider | None = None,
                 ledger: Ledger | None = None, prices: Prices | None = None):
        if not spec.provider or not spec.model:
            raise ValueError("LLM agent needs spec.provider and spec.model")
        self.spec = spec
        self.paraphrase = int(spec.params.get("paraphrase", 0)) % 3
        self.max_tokens = int(spec.params.get("max_tokens", DEFAULT_MAX_TOKENS))
        # memory: "full" (default) keeps one append-only conversation for the run;
        # "window:N" starts a fresh conversation every N rounds whose first turn
        # carries the whole public history table. At round 100 a "full" prompt is
        # ~31k tokens (mostly cached); "window:10" keeps it under ~7k.
        mem = str(spec.params.get("memory", "full"))
        self.window = int(mem.split(":", 1)[1]) if mem.startswith("window:") else 0
        self.provider = provider or make_provider(spec.provider, extra_body=spec.params.get("extra_body"))
        self.ledger = ledger if ledger is not None else get_ledger()
        self.prices = prices or Prices.load()
        self.prices.model(spec.provider, spec.model)  # fail now if the model is unpriced
        self._reset()

    def _reset(self) -> None:
        self.system: str | None = None
        self.messages: list[dict] = []
        self.framing: dict | None = None
        self.last_history_round = 0
        self.pending_note: str | None = None
        self.epoch_start_round = 0
        self.last_prompt_tokens = 0     # actual input+output of the latest call, for estimates
        self.totals = {"calls": 0, "input": 0, "cached": 0, "output": 0, "usd": 0.0, "fallbacks": 0, "retries": 0}

    # ---- Agent interface ----------------------------------------------------

    def act(self, obs: Observation) -> Action:
        rules = prompts.rules_for(obs, self.spec.params)
        with_pm = obs.phase == "prebid" and prompts.private_message_available(obs.framing)
        turn = self._user_turn(obs, with_pm)   # may start a new epoch (replaces self.messages)
        self.messages.append({"role": "user", "content": turn})
        schema = schema_for(obs, rules, with_pm)
        usage = {"input": 0, "cached": 0, "output": 0, "usd": 0.0, "model": self.spec.model,
                 "provider": self.spec.provider, "reasoning": self.spec.reasoning,
                 "paraphrase": self.paraphrase, "calls": 0, "retries": 0, "fallback": False, "errors": []}
        action, error = None, None
        for attempt in range(2):
            if attempt:
                usage["retries"] += 1
                self.messages.append({"role": "user", "content": prompts.text("retry", error=error)})
            reply = self._call(schema, usage)
            if reply is None:            # API error: already logged in usage["errors"]
                error = "the reply did not arrive"
                continue
            self.messages.append({"role": "assistant", "content": reply or "(empty)"})
            try:
                action = parse_action(reply, obs, rules, with_pm)
                break
            except ValueError as e:
                error = str(e)
                usage["errors"].append({"invalid": error, "reply": reply[:300]})
        if action is None:
            action, what = fallback_action(obs)
            usage["fallback"] = True
            self.totals["fallbacks"] += 1
            self.pending_note = prompts.text("fallback_note", what=what)
        self.totals["retries"] += usage["retries"]
        if not usage["errors"]:
            del usage["errors"]
        action.usage = usage
        return action

    def snapshot(self) -> dict:
        return json.loads(json.dumps({
            "version": SNAPSHOT_VERSION, "spec": asdict(self.spec), "system": self.system,
            "messages": self.messages, "framing": self.framing,
            "last_history_round": self.last_history_round, "pending_note": self.pending_note,
            "epoch_start_round": self.epoch_start_round,
            "last_prompt_tokens": self.last_prompt_tokens, "totals": self.totals,
        }))

    def restore(self, state: dict) -> None:
        if state.get("version") != SNAPSHOT_VERSION:
            raise ValueError(f"unsupported snapshot version {state.get('version')!r}")
        self._reset()
        self.system = state["system"]
        self.messages = [dict(m) for m in state["messages"]]
        self.framing = dict(state["framing"]) if state["framing"] is not None else None
        self.last_history_round = state["last_history_round"]
        self.pending_note = state["pending_note"]
        self.epoch_start_round = state.get("epoch_start_round", 0)
        self.last_prompt_tokens = state["last_prompt_tokens"]
        self.totals = dict(state["totals"])

    # ---- internals ------------------------------------------------------------

    def _user_turn(self, obs: Observation, with_pm: bool) -> str:
        parts: list[str] = []
        if self.window and self.system is not None and obs.round - self.epoch_start_round >= self.window \
                and obs.phase == "prebid":
            # New epoch: drop the conversation, re-render the system prompt with
            # the current framing, and show the full history table again.
            self.system, self.messages, self.last_history_round = None, [], 0
            self.last_prompt_tokens = 0
        if self.system is None:
            self.epoch_start_round = obs.round
            self.system = prompts.render_system(obs, self.paraphrase, self.spec.params)
            self.framing = dict(obs.framing)
        elif obs.framing != self.framing:
            parts.append(prompts.render_framing_update(obs.framing, self.paraphrase))
            self.framing = dict(obs.framing)
        if self.pending_note:
            parts.append(self.pending_note)
            self.pending_note = None
        new_rows = [r for i, r in enumerate(obs.history, 1) if r.get("round", i) > self.last_history_round]
        if new_rows:
            header = prompts.text("history_header" if self.last_history_round == 0 else "history_more")
            parts.append(header + "\n" + prompts.render_history(new_rows))
            self.last_history_round = max(r.get("round", i) for i, r in enumerate(obs.history, 1))
        if obs.messages:
            parts.append(prompts.render_messages(obs.messages))
        if obs.fines:
            parts.append(prompts.text("fines", fines=f"{obs.fines:g}"))
        parts.append(prompts.render_turn(obs, self.spec.params, with_pm))
        return "\n\n".join(parts)

    def estimate_input_tokens(self) -> int:
        if self.last_prompt_tokens:
            # The previous call's prompt plus its reply is an exact-ish prefix;
            # only the turns appended since then are estimated from characters.
            tail, n = [], 0
            for m in reversed(self.messages):
                if m["role"] == "assistant":
                    break
                tail.append(m["content"])
            n = sum(estimate_tokens(t) for t in tail)
            return self.last_prompt_tokens + n + 16
        return estimate_tokens(self.system or "") + sum(estimate_tokens(m["content"]) for m in self.messages) + 16

    def _complete_with_backoff(self, schema: dict, usage: dict):
        """Rate limits (429) are waited out here, on top of the SDK's own short
        retries: low-balance accounts allow only a few requests per minute.
        A 429 is rejected unbilled, so the reservation simply stays open."""
        waits = int(self.spec.params.get("rate_limit_retries", 6))
        delay = float(self.spec.params.get("rate_limit_wait_s", 20.0))
        for attempt in range(waits + 1):
            try:
                return self.provider.complete(model=self.spec.model, system=self.system, messages=self.messages,
                                              json_schema=schema, max_tokens=self.max_tokens,
                                              reasoning=self.spec.reasoning)
            except Exception as e:  # noqa: BLE001
                if getattr(e, "status_code", None) != 429 or attempt == waits:
                    raise
                usage["rate_limited"] = usage.get("rate_limited", 0) + 1
                time.sleep(delay)
                delay = min(delay * 1.5, 120.0)

    def _call(self, schema: dict, usage: dict) -> str | None:
        p, model = self.spec.provider, self.spec.model
        est = self.prices.estimate(p, model, self.estimate_input_tokens(), self.max_tokens)
        ticket = self.ledger.reserve(p, est)          # BudgetExceeded propagates
        t0 = time.time()
        try:
            comp = self._complete_with_backoff(schema, usage)
        except BudgetExceeded:
            self.ledger.release(ticket)
            raise
        except Exception as e:  # noqa: BLE001 - every provider error is logged, never fatal
            status = getattr(e, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 408:
                self.ledger.release(ticket)        # rejected requests are not billed
            else:                                   # timeouts etc. may have been billed
                self.ledger.settle(ticket, est, {"error": type(e).__name__, "model": model})
                usage["usd"] += est
            usage["calls"] += 1
            usage.setdefault("errors", []).append({"api": type(e).__name__, "status": status, "detail": str(e)[:300]})
            return None
        actual = self.prices.cost(p, model, comp.usage)
        self.ledger.settle(ticket, actual, {**comp.usage, "model": model})
        usage["calls"] += 1
        usage["latency_s"] = round(usage.get("latency_s", 0.0) + time.time() - t0, 3)
        for k in ("input", "cached", "output"):
            usage[k] += int(comp.usage.get(k, 0))
            self.totals[k] += int(comp.usage.get(k, 0))
        usage["usd"] += actual
        self.totals["usd"] += actual
        self.totals["calls"] += 1
        if comp.finish:
            usage["finish"] = comp.finish
        if comp.usage.get("refusal"):
            usage["refusal"] = comp.usage["refusal"]
        self.last_prompt_tokens = int(comp.usage.get("input", 0)) + int(comp.usage.get("output", 0))
        return comp.text


def make_agent(spec: AgentSpec, firm: int = 0, config=None, **kwargs) -> LLMAgent:
    """Factory the engine calls for kind == "llm" (testbed.engine.factory).
    Firm and config are unused: game parameters arrive in Observation.rules."""
    return LLMAgent(spec, **kwargs)
