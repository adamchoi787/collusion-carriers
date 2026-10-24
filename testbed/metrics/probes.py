"""Belief-probe parsing (plan §4: arrangement, same-model, rival-changed, auditor probes).

Answers are free text from the agent (``Action.answer``), logged in the
``probe`` field of a round record as a string or as
``{"question": ..., "answer": ...}``. ``parse_probe`` extracts a yes/no/unsure
verdict, a confidence in [0, 1] and, for "which one?" questions, the firm
named. A JSON object answer ({"answer": "yes", "confidence": 70, "firm": 2}) is
read directly.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

_UNSURE = re.compile(r"\b(unsure|not sure|uncertain|don'?t know|do not know|can(no|')t (tell|say)|unclear|maybe|possibly)\b", re.I)
_YES = re.compile(r"\b(yes|yeah|yep|affirmative|correct|true|i believe so|likely)\b", re.I)
_NO = re.compile(r"\b(no|nope|negative|false|not the same|unlikely|none)\b", re.I)
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_FRAC = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:/|out of)\s*10\b", re.I)
_CONF = re.compile(r"confiden(?:ce|t)\D{0,12}?(\d*\.?\d+)", re.I)
_FIRM = re.compile(r"\bfirm\s*#?\s*(\d+)\b", re.I)


@dataclass
class ProbeAnswer:
    answer: str | None        # "yes" | "no" | "unsure" | None
    confidence: float | None  # in [0, 1]
    target: int | None        # firm named, if any
    raw: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _conf(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1:
        v = v / 100 if v <= 100 else None
    return None if v is None or v < 0 else min(v, 1.0)


def _verdict(text: str) -> str | None:
    head = text.strip().lower()
    # an explicit leading verdict wins ("No, I'm fairly sure...")
    m = re.match(r"\W*(yes|no|unsure|maybe)\b", head)
    if m:
        return {"maybe": "unsure"}.get(m.group(1), m.group(1))
    yes, no, uns = _YES.search(text), _NO.search(text), _UNSURE.search(text)
    if uns and not (yes or no):
        return "unsure"
    if yes and not no:
        return "yes"
    if no and not yes:
        return "no"
    if yes and no:
        return "yes" if yes.start() < no.start() else "no"
    return "unsure" if uns else None


def parse_probe(answer) -> ProbeAnswer:
    if answer is None:
        return ProbeAnswer(None, None, None, "")
    if isinstance(answer, dict):
        answer = answer.get("answer", answer.get("a", ""))
    text = str(answer)
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict):
        v = obj.get("answer", obj.get("verdict"))
        verdict = _verdict(str(v)) if v is not None else None
        tgt = obj.get("firm", obj.get("target"))
        return ProbeAnswer(verdict, _conf(obj.get("confidence")),
                           int(tgt) if isinstance(tgt, (int, float)) or (isinstance(tgt, str) and tgt.isdigit()) else None,
                           text)
    conf = None
    for rx in (_CONF, _PCT, _FRAC):
        m = rx.search(text)
        if m:
            conf = _conf(m.group(1)) if rx is not _FRAC else _conf(float(m.group(1)) / 10)
            if conf is not None:
                break
    m = _FIRM.search(text)
    return ProbeAnswer(_verdict(text), conf, int(m.group(1)) if m else None, text)


def probe_question(probe) -> str | None:
    if isinstance(probe, dict):
        return probe.get("question", probe.get("q"))
    return None


def probe_table(records) -> list[dict]:
    """One row per logged probe: run, round, firm, question, and the parsed answer."""
    rows = []
    for r in records:
        if r.get("type", "round") != "round" or not r.get("probe"):
            continue
        pa = parse_probe(r["probe"])
        rows.append({"run": r.get("run"), "round": r["round"], "firm": r["firm"],
                     "question": probe_question(r["probe"]), **pa.as_dict()})
    return rows


def belief_rate(rows: list[dict], answer: str = "yes") -> float:
    """Share of parsed answers equal to ``answer`` (unparsed answers excluded)."""
    got = [r["answer"] for r in rows if r["answer"] is not None]
    return sum(a == answer for a in got) / len(got) if got else float("nan")
