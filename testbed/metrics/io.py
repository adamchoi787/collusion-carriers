"""Load JSONL run logs (CONTRACT.md, "Log") into plain record dicts.

Every returned record gets a ``"run"`` key ("<card_id>/<seed>" from the header,
or the file path when the header lacks them). Header lines are kept (they have
``type == "header"``) so that ``build_panel`` can read the cost support and
reserve; metric functions skip them.

Schema assumptions made here (the engine is built in parallel; adjust in one
place if it differs):

* ``shown`` keys are rival firm ids (strings after a JSON round-trip);
  values are ``{medium: int | "unavailable"}``.
* ``bids`` is one entry per contract, ``None`` for no bid.
* ``won`` is one boolean per contract. A list of won contract indices is also
  accepted when its length differs from K.
* ``price`` is one entry per contract (winning price or ``None``) or absent.
* ``profit`` is this firm's profit this round (all contracts), before fines.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def read_jsonl(path: str | Path) -> list[dict]:
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_run(path: str | Path, run_id: str | None = None) -> list[dict]:
    """All lines of one run log, each tagged with ``run``."""
    lines = read_jsonl(path)
    header = next((r for r in lines if r.get("type") == "header"), None)
    if run_id is None:
        cfg = (header or {}).get("config") or {}
        if "card_id" in cfg and "seed" in cfg:
            run_id = f"{cfg['card_id']}/{cfg['seed']}"
        else:
            run_id = str(path)
    for r in lines:
        r["run"] = run_id
    return lines


def load_runs(paths: Iterable[str | Path]) -> list[dict]:
    out: list[dict] = []
    for p in paths:
        out.extend(load_run(p))
    return out


def load_cell(directory: str | Path) -> list[dict]:
    """Every ``<seed>.jsonl`` under ``runs/<card_id>/``: one cell, pooled."""
    return load_runs(sorted(Path(directory).glob("*.jsonl")))


def write_jsonl(records: Iterable[dict], path: str | Path) -> None:
    """Write records (header first, as produced by synthetic.to_records)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps({k: v for k, v in r.items() if k != "run"}) + "\n")


def round_records(records: Iterable[dict]) -> list[dict]:
    return [r for r in records if r.get("type", "round") == "round"]


def headers(records: Iterable[dict]) -> dict[str, dict]:
    return {r["run"]: r for r in records if r.get("type") == "header"}
