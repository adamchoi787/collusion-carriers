"""Where logs and checkpoints go.

The engine only talks to the `Storage` protocol below. `LocalStorage` writes
`<root>/<card_id>/<seed>.jsonl`; root defaults to $TESTBED_RUNS_DIR, else `runs/`. On Modal, a Volume is
mounted as a directory, so the runner can use `LocalStorage(root="/vol/runs")`
and override `commit()` to call `volume.commit()`; or it can implement the
protocol directly.
"""
from __future__ import annotations

import json
import os
from typing import Protocol


class LogSink(Protocol):
    def write(self, record: dict) -> None: ...   # one JSON object per line
    def close(self) -> None: ...                 # flush; the log is complete


class Storage(Protocol):
    def open_log(self, card_id: str, seed: int) -> LogSink:
        """Start (truncate) the run log for this card and seed."""
    def save_checkpoint(self, card_id: str, seed: int, round: int, data: dict) -> str:
        """Persist a JSON-serialisable checkpoint; return a key for load_checkpoint."""
    def load_checkpoint(self, key: str) -> dict: ...
    def commit(self) -> None:
        """Make everything written so far durable (no-op locally)."""


def dumps(record: dict) -> str:
    return json.dumps(record, separators=(",", ":"), allow_nan=False)


class _FileSink:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self._f = open(path, "w")

    def write(self, record: dict) -> None:
        self._f.write(dumps(record) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


class LocalStorage:
    def __init__(self, root: str | None = None):
        self.root = root or os.environ.get("TESTBED_RUNS_DIR") or "runs"

    def log_path(self, card_id: str, seed: int) -> str:
        return os.path.join(self.root, card_id, f"{seed}.jsonl")

    def open_log(self, card_id: str, seed: int) -> LogSink:
        return _FileSink(self.log_path(card_id, seed))

    def save_checkpoint(self, card_id: str, seed: int, round: int, data: dict) -> str:
        path = os.path.join(self.root, card_id, f"{seed}.r{round}.ckpt.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(dumps(data))
        return path

    def load_checkpoint(self, key: str) -> dict:
        """`key` is the path save_checkpoint returned (absolute, or relative to the cwd)."""
        with open(key) as f:
            return json.load(f)

    def commit(self) -> None:
        pass


class _MemorySink:
    def __init__(self, lines: list[str]):
        self.lines = lines

    def write(self, record: dict) -> None:
        self.lines.append(dumps(record))

    def close(self) -> None:
        pass


class MemoryStorage:
    """Keeps everything in memory; for tests and quick in-process runs."""

    def __init__(self):
        self.logs: dict[tuple[str, int], list[str]] = {}
        self.checkpoints: dict[str, str] = {}

    def open_log(self, card_id: str, seed: int) -> LogSink:
        self.logs[(card_id, seed)] = lines = []
        return _MemorySink(lines)

    def records(self, card_id: str, seed: int) -> list[dict]:
        return [json.loads(line) for line in self.logs[(card_id, seed)]]

    def save_checkpoint(self, card_id: str, seed: int, round: int, data: dict) -> str:
        key = f"{card_id}/{seed}.r{round}"
        self.checkpoints[key] = dumps(data)
        return key

    def load_checkpoint(self, key: str) -> dict:
        return json.loads(self.checkpoints[key])

    def commit(self) -> None:
        pass


def read_log(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]
