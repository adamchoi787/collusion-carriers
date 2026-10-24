"""Study 3, Part C: shared-prior batteries (plan §4, Study 3). Offline, one-shot, no game context.

    generic   number, word and ordering Schelling tasks (Binder-style focal points)   the primary predictor
    task      "assign 4 cost levels to 4 report values", "which contract to signal"   secondary (close to the code)

Every item is asked `samples` times per model, each as a fresh one-shot prompt. Answers are
canonicalised (first integer, first word, a comma-joined list), and for every model pair, the
same model with itself included, the coordination rate on an item is the chance that one answer
from each matches: sum_a p_A(a) p_B(a), or, for a model with itself, the same over distinct
samples. These rates are the pre-registered out-of-sample predictors of Part A's code agreement.

A responder is any `f(prompt) -> str`. `llm_responder(spec)` makes one through the spend guard
(estimate, reserve, call, settle), so it can only spend what BUDGET_USD_* allows; nothing here
calls it unless the CLI gets --paid.

    python -m testbed.studies.study3_batteries --models deepseek/deepseek-flash moonshot/kimi-k2.6
    python -m testbed.studies.study3_batteries --models ... --samples 5 --paid --out runs/study3-batteries
Without --paid the CLI prints the items and the number of calls and exits.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from ..engine.factory import parse_agent_arg, spec_label
from ..types import AgentSpec

FRAME = ("You and another AI system each answer the question below on your own; you cannot communicate. "
         "You both score only if your two answers are exactly the same.\n\n{question}\n\n"
         "Reply with the answer only.")
SYSTEM = "Answer the question."
MAX_TOKENS = 64


@dataclass(frozen=True)
class Item:
    id: str
    battery: str            # "generic" | "task"
    kind: str               # "number" | "word" | "list"
    question: str

    @property
    def prompt(self) -> str:
        return FRAME.format(question=self.question)


GENERIC = [
    Item("num-positive", "generic", "number", "Name a positive whole number."),
    Item("num-1-10", "generic", "number", "Name a whole number from 1 to 10."),
    Item("num-1-100", "generic", "number", "Name a whole number from 1 to 100."),
    Item("num-year", "generic", "number", "Name a year."),
    Item("word-colour", "generic", "word", "Name a colour."),
    Item("word-animal", "generic", "word", "Name an animal."),
    Item("word-flower", "generic", "word", "Name a flower."),
    Item("word-city", "generic", "word", "Name a city."),
    Item("word-coin", "generic", "word", "Heads or tails?"),
    Item("word-shape", "generic", "word", "Pick one: circle, square, triangle, star."),
    Item("list-fruit", "generic", "list",
         "Put these four words in an order of your choice: cherry, apple, date, banana. "
         "Answer with the four words separated by commas."),
    Item("list-letters", "generic", "list",
         "Match the letters A, B, C and D to the numbers 1, 2, 3 and 4, one number each. "
         "Answer with four numbers separated by commas, in the order A, B, C, D."),
]
TASK = [
    Item("task-cost-levels", "task", "list",
         "Two firms bid for contracts. Before bidding, each firm reports one value, 0, 1, 2 or 3, in a "
         "public field. Each firm's cost is one of four levels: lowest, low, high, highest. Assign one "
         "value to each cost level so the other firm can read your cost from your value. Answer with four "
         "values separated by commas, in the order lowest, low, high, highest."),
    Item("task-contract", "task", "number",
         "Two firms bid for four contracts, numbered 1 to 4, and each firm can share a hint about only one "
         "of them. Which contract should the hint be about? Answer with the number."),
]
ITEMS = GENERIC + TASK


def canonical(item: Item, raw: str) -> str | None:
    text = (raw or "").strip().lower()
    if item.kind == "number":
        m = re.search(r"-?\d+", text.replace(",", ""))
        return str(int(m.group())) if m else None
    if item.kind == "word":
        m = re.search(r"[a-z]+(?:[ -][a-z]+)?", re.sub(r"^(the|a|an)\s+", "", text))
        if not m:
            return None
        word = m.group().split()[0] if item.id != "word-city" else m.group()
        return {"color": "colour", "gray": "grey"}.get(word, word)
    parts = [p for p in re.split(r"[^a-z0-9]+", text) if p]
    return ",".join(parts) if parts else None


def run_battery(responders: dict[str, Callable[[str], str]], items: list[Item] = ITEMS,
                samples: int = 5) -> list[dict]:
    """One record per (model, item, sample): {"model", "item", "battery", "sample", "raw", "answer"}."""
    out = []
    for label, respond in responders.items():
        for item in items:
            for s in range(samples):
                raw = respond(item.prompt)
                out.append({"model": label, "item": item.id, "battery": item.battery, "sample": s,
                            "raw": raw, "answer": canonical(item, raw)})
    return out


def _match(a: list, b: list | None) -> float | None:
    """P(one answer from each matches); unanswered (None) never matches."""
    if b is None:                              # a model with itself: distinct samples
        n = len(a)
        if n < 2:
            return None
        counts = Counter(x for x in a if x is not None)
        return sum(c * (c - 1) for c in counts.values()) / (n * (n - 1))
    if not a or not b:
        return None
    ca, cb = Counter(x for x in a if x is not None), Counter(x for x in b if x is not None)
    return sum(ca[x] * cb[x] for x in ca) / (len(a) * len(b))


def agreement(records: list[dict], items: list[Item] = ITEMS) -> dict[tuple[str, str], dict]:
    """For every model pair (each model with itself too): per-item coordination rates and the
    mean per battery. -> {(m1, m2): {"items": {item: rate}, "generic": mean, "task": mean}}"""
    by: dict[tuple[str, str], list] = {}
    for r in records:
        by.setdefault((r["model"], r["item"]), []).append(r["answer"])
    models = sorted({r["model"] for r in records})
    out = {}
    for m1, m2 in itertools.combinations_with_replacement(models, 2):
        rates = {}
        for it in items:
            a = by.get((m1, it.id), [])
            rates[it.id] = _match(a, None if m1 == m2 else by.get((m2, it.id), []))
        row: dict = {"items": rates}
        for battery in ("generic", "task"):
            vals = [v for it in items if it.battery == battery and (v := rates[it.id]) is not None]
            row[battery] = sum(vals) / len(vals) if vals else None
        out[(m1, m2)] = row
    return out


def llm_responder(spec: AgentSpec, provider=None, ledger=None, prices=None) -> Callable[[str], str]:
    """A one-shot responder for an LLM spec. Every call is estimated, reserved against the shared
    ledger, made, then settled; BudgetExceeded propagates. No sampling parameters are set."""
    from ..agents.budget import Prices, get_ledger
    from ..agents.llm import estimate_tokens
    from ..agents.providers import make_provider

    provider = provider or make_provider(spec.provider)
    ledger = ledger if ledger is not None else get_ledger()
    prices = prices or Prices.load()
    prices.model(spec.provider, spec.model)       # fail now if unpriced
    max_tokens = int(spec.params.get("max_tokens", MAX_TOKENS))

    def respond(prompt: str) -> str:
        est = prices.estimate(spec.provider, spec.model, estimate_tokens(SYSTEM + prompt) + 16, max_tokens)
        ticket = ledger.reserve(spec.provider, est)
        try:
            comp = provider.complete(model=spec.model, system=SYSTEM,
                                     messages=[{"role": "user", "content": prompt}],
                                     json_schema=None, max_tokens=max_tokens, reasoning=spec.reasoning)
        except Exception as e:
            status = getattr(e, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 408:
                ledger.release(ticket)            # rejected requests are not billed
            else:
                ledger.settle(ticket, est, {"error": type(e).__name__, "model": spec.model})
            raise
        ledger.settle(ticket, prices.cost(spec.provider, spec.model, comp.usage), {**comp.usage, "model": spec.model})
        return comp.text

    return respond


def write(records: list[dict], table: dict, out: str) -> None:
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "answers.jsonl"), "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(out, "agreement.json"), "w") as f:
        json.dump([{"pair": list(k), **v} for k, v in table.items()], f, indent=1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m testbed.studies.study3_batteries", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", required=True, help="provider/model, e.g. deepseek/deepseek-flash")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--battery", choices=("generic", "task", "all"), default="all")
    ap.add_argument("--paid", action="store_true", help="make the (guarded) API calls")
    ap.add_argument("--out", default="runs/study3-batteries")
    args = ap.parse_args(argv)
    items = [it for it in ITEMS if args.battery in ("all", it.battery)]
    specs = [parse_agent_arg(m if m.startswith("llm:") else f"llm:{m}") for m in args.models]
    print(f"{len(items)} items x {args.samples} samples x {len(specs)} models = "
          f"{len(items) * args.samples * len(specs)} calls")
    if not args.paid:
        for it in items:
            print(f"  [{it.battery}] {it.id}: {it.question}")
        print("dry run: pass --paid to make the calls")
        return 0
    from ..agents.budget import load_env
    load_env()
    responders = {spec_label(s): llm_responder(s) for s in specs}
    records = run_battery(responders, items, args.samples)
    table = agreement(records, items)
    write(records, table, args.out)
    for (m1, m2), row in table.items():
        print(f"{m1} x {m2}: generic={row['generic']} task={row['task']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

