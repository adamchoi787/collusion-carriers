"""Hard spend guard over one shared ledger.

Every paid call goes reserve -> call -> settle (or release):

    ticket = ledger.reserve("anthropic", est_usd)   # raises BudgetExceeded
    ...call the API...
    ledger.settle(ticket, actual_usd, usage)          # or ledger.release(ticket)

A reservation counts against the caps until it is settled or released, so
parallel callers (threads, processes, Modal containers) can never jointly
exceed a cap. Caps come from BUDGET_USD_TOTAL and BUDGET_USD_<PROVIDER>
(`.env` locally, the Modal Secret `collusion-api-keys` on Modal). A missing,
unparsable or zero cap blocks every paid call.

Backends:
  * LocalLedger: `runs/ledger.jsonl`, an append-only event log under a file lock.
  * ModalLedger: a `modal.Dict`, with a lock key taken by an atomic
    put(skip_if_exists=True), so reserve and settle are atomic across containers.

Key values are never read here except to test for presence.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PRICES_PATH = Path(__file__).with_name("prices.yaml")
PROVIDERS = ("deepseek", "minimax", "openai", "anthropic", "moonshot")
MODAL_DICT_NAME = "collusion-ledger"


class BudgetExceeded(RuntimeError):
    """A paid call was refused because it could exceed a cap."""


class UnknownPrice(BudgetExceeded):
    """The model has no row in prices.yaml, so its cost cannot be bounded."""


def load_env() -> None:
    """Load `.env` from the repo root without overriding variables already set
    (on Modal the Secret has already populated the environment)."""
    path = REPO_ROOT / ".env"
    if path.exists():
        from dotenv import load_dotenv

        load_dotenv(path, override=False)


def key_present(provider: str) -> bool:
    load_env()
    env = Prices.load().provider(provider).get("key_env", f"{provider.upper()}_API_KEY")
    return bool(os.environ.get(env, "").strip())


# ---- prices -----------------------------------------------------------------

class Prices:
    def __init__(self, table: dict):
        self.table = table

    @classmethod
    def load(cls, path: Path | None = None) -> "Prices":
        with open(path or PRICES_PATH) as f:
            return cls(yaml.safe_load(f))

    def provider(self, provider: str) -> dict:
        return self.table.get("providers", {}).get(provider, {})

    def model(self, provider: str, model: str) -> dict:
        row = self.provider(provider).get("models", {}).get(model)
        if row is None:
            raise UnknownPrice(f"no price for {provider}/{model} in prices.yaml; add a row before calling it")
        return row

    def estimate(self, provider: str, model: str, input_tokens: int, max_output_tokens: int) -> float:
        """Worst-case cost: every input token uncached, the full output allowance used."""
        row = self.model(provider, model)
        return (input_tokens * row["input"] + max_output_tokens * row["output"]) / 1e6

    def cost(self, provider: str, model: str, usage: dict) -> float:
        """Actual cost from usage {input, cached, output, cache_write?}.
        `input` is the total prompt tokens, including cached and cache-write ones."""
        row = self.model(provider, model)
        cached = usage.get("cached", 0) or 0
        write = usage.get("cache_write", 0) or 0
        plain = max(0, (usage.get("input", 0) or 0) - cached - write)
        cached_price = row["cached"] if row.get("cached") is not None else row["input"]
        write_mult = self.provider(provider).get("cache_write_multiplier", 1.0)
        return (plain * row["input"] + cached * cached_price + write * row["input"] * write_mult
                + (usage.get("output", 0) or 0) * row["output"]) / 1e6

    def compute_cost(self, seconds: float, cpu: float, memory_gib: float) -> float:
        m = self.table.get("modal", {})
        return seconds * (cpu * m.get("cpu_core_second", 0.0) + memory_gib * m.get("memory_gib_second", 0.0))


# ---- caps -------------------------------------------------------------------

def _parse_cap(raw: str | None) -> float:
    try:
        v = float(raw) if raw is not None else 0.0
    except ValueError:
        return 0.0
    return v if v > 0 else 0.0


@dataclass
class Caps:
    total: float = 0.0
    per_provider: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Caps":
        load_env()
        return cls(
            total=_parse_cap(os.environ.get("BUDGET_USD_TOTAL")),
            per_provider={p: _parse_cap(os.environ.get(f"BUDGET_USD_{p.upper()}")) for p in PROVIDERS},
        )

    def for_provider(self, provider: str) -> float:
        return self.per_provider.get(provider, 0.0)


# ---- ledger -----------------------------------------------------------------

@dataclass
class Ticket:
    id: str
    provider: str
    usd: float
    ts: float

    def to_dict(self) -> dict:
        return asdict(self)


def _empty_state() -> dict:
    return {"providers": {}, "compute": {"usd": 0.0, "seconds": 0.0, "jobs": 0}}


def _prov(state: dict, provider: str) -> dict:
    return state["providers"].setdefault(provider, {
        "settled_usd": 0.0, "reserved": {}, "calls": 0,
        "input": 0, "cached": 0, "output": 0, "errors": 0,
    })


def _committed(p: dict) -> float:
    return p["settled_usd"] + sum(r["usd"] for r in p["reserved"].values())


def apply_event(state: dict, ev: dict) -> None:
    """Fold one ledger event into the state. Shared by both backends."""
    kind = ev["ev"]
    if kind == "compute":
        c = state["compute"]
        c["usd"] += ev["usd"]
        c["seconds"] += ev["seconds"]
        c["jobs"] += 1
        return
    p = _prov(state, ev["p"])
    if kind == "reserve":
        p["reserved"][ev["t"]] = {"usd": ev["usd"], "ts": ev["ts"]}
    elif kind == "settle":
        p["reserved"].pop(ev["t"], None)
        p["settled_usd"] += ev["usd"]
        p["calls"] += 1
        u = ev.get("usage") or {}
        for k in ("input", "cached", "output"):
            p[k] += int(u.get(k, 0) or 0)
        if u.get("error"):
            p["errors"] += 1
    elif kind == "release":
        p["reserved"].pop(ev["t"], None)


class Ledger:
    """Shared logic; backends supply _locked(), _read() and _write()."""

    def __init__(self, caps: Caps | None = None):
        self.caps = caps if caps is not None else Caps.from_env()

    # backend hooks
    def _locked(self) -> contextlib.AbstractContextManager:
        raise NotImplementedError

    def _read(self) -> dict:
        raise NotImplementedError

    def _write(self, state: dict, ev: dict) -> None:
        raise NotImplementedError

    def _commit(self, ev: dict) -> dict:
        state = self._read()
        apply_event(state, ev)
        self._write(state, ev)
        return state

    # public interface
    def reserve(self, provider: str, est_usd: float) -> Ticket:
        if est_usd < 0:
            raise ValueError("estimate must be non-negative")
        cap_p, cap_t = self.caps.for_provider(provider), self.caps.total
        if cap_p <= 0 or cap_t <= 0:
            raise BudgetExceeded(f"{provider}: cap is 0 or unset (BUDGET_USD_{provider.upper()}={cap_p}, TOTAL={cap_t})")
        with self._locked():
            state = self._read()
            used_p = _committed(_prov(state, provider))
            used_t = sum(_committed(p) for p in state["providers"].values())
            if used_p + est_usd > cap_p:
                raise BudgetExceeded(f"{provider}: ${used_p:.4f} committed + ${est_usd:.4f} would exceed cap ${cap_p:.2f}")
            if used_t + est_usd > cap_t:
                raise BudgetExceeded(f"total: ${used_t:.4f} committed + ${est_usd:.4f} would exceed cap ${cap_t:.2f}")
            t = Ticket(uuid.uuid4().hex, provider, float(est_usd), time.time())
            self._commit({"ev": "reserve", "t": t.id, "p": provider, "usd": t.usd, "ts": t.ts})
        return t

    def settle(self, ticket: Ticket, actual_usd: float, usage: dict | None = None) -> None:
        keep = {k: usage[k] for k in ("input", "cached", "output", "model", "error") if usage and k in usage}
        with self._locked():
            self._commit({"ev": "settle", "t": ticket.id, "p": ticket.provider, "usd": float(actual_usd),
                          "usage": keep, "ts": time.time()})

    def release(self, ticket: Ticket) -> None:
        with self._locked():
            self._commit({"ev": "release", "t": ticket.id, "p": ticket.provider, "ts": time.time()})

    def record_compute(self, job: str, seconds: float, usd: float) -> None:
        with self._locked():
            self._commit({"ev": "compute", "job": job, "seconds": float(seconds), "usd": float(usd), "ts": time.time()})

    def release_stale(self, older_than_s: float) -> int:
        """Release reservations left behind by crashed callers. Manual only:
        a stale reservation keeps counting (conservatively) until this is run."""
        cutoff = time.time() - older_than_s
        n = 0
        with self._locked():
            state = self._read()
            for prov, p in state["providers"].items():
                for t, r in list(p["reserved"].items()):
                    if r["ts"] < cutoff:
                        state = self._commit({"ev": "release", "t": t, "p": prov, "ts": time.time(), "stale": True})
                        n += 1
        return n

    def summary(self) -> dict:
        with self._locked():
            return self._read()


class LocalLedger(Ledger):
    def __init__(self, path: Path | str | None = None, caps: Caps | None = None):
        super().__init__(caps)
        self.path = Path(path) if path else REPO_ROOT / "runs" / "ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lockfile = self.path.with_suffix(".lock")
        self._tlock = threading.RLock()
        self._depth = 0
        self._fd: Any = None

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        with self._tlock:  # re-entrant within a thread; flock across processes
            if self._depth == 0:
                self._fd = open(self._lockfile, "a")
                fcntl.flock(self._fd, fcntl.LOCK_EX)
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
                    self._fd.close()
                    self._fd = None

    def _read(self) -> dict:
        state = _empty_state()
        if self.path.exists():
            with open(self.path) as f:
                for line in f:
                    if line.strip():
                        apply_event(state, json.loads(line))
        return state

    def _write(self, state: dict, ev: dict) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(ev, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())


class ModalLedger(Ledger):
    """Ledger in a modal.Dict. `store` may be any object with modal.Dict's
    get/put(skip_if_exists=)/pop, which lets tests use an in-memory fake."""

    LOCK_KEY, STATE_KEY = "lock", "state"
    STALE_LOCK_S = 30.0

    def __init__(self, store: Any = None, caps: Caps | None = None, name: str = MODAL_DICT_NAME):
        super().__init__(caps)
        if store is None:
            import modal

            store = modal.Dict.from_name(name, create_if_missing=True)
        self.store = store
        self._tlock = threading.RLock()
        self._depth = 0

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        with self._tlock:
            if self._depth == 0:
                self._acquire()
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    self.store.pop(self.LOCK_KEY)

    def _acquire(self) -> None:
        token = {"owner": uuid.uuid4().hex, "ts": time.time()}
        delay = 0.01
        while not self.store.put(self.LOCK_KEY, token, skip_if_exists=True):
            held = self.store.get(self.LOCK_KEY)
            # Break a lock whose holder died mid-critical-section. The section is
            # one get and one put, so 30 s means the holder is gone.
            if held is not None and time.time() - held.get("ts", 0) > self.STALE_LOCK_S:
                with contextlib.suppress(KeyError):
                    self.store.pop(self.LOCK_KEY)
            time.sleep(delay)
            delay = min(delay * 2, 0.5)
            token["ts"] = time.time()

    def _read(self) -> dict:
        return self.store.get(self.STATE_KEY) or _empty_state()

    def _write(self, state: dict, ev: dict) -> None:
        self.store.put(self.STATE_KEY, state)


class CappedLedger(Ledger):
    """Wraps another ledger with an extra local cap (e.g. $0.50 for a smoke
    run). Both this cap and the shared caps must allow a reservation."""

    def __init__(self, inner: Ledger, max_usd: float):
        self.inner, self.max_usd, self.spent = inner, max_usd, 0.0
        self.caps = inner.caps
        self._open: dict[str, float] = {}
        self._lock = threading.Lock()

    def reserve(self, provider: str, est_usd: float) -> Ticket:
        with self._lock:
            committed = self.spent + sum(self._open.values())
            if committed + est_usd > self.max_usd:
                raise BudgetExceeded(f"run cap: ${committed:.4f} + ${est_usd:.4f} would exceed ${self.max_usd:.2f}")
            t = self.inner.reserve(provider, est_usd)
            self._open[t.id] = est_usd
            return t

    def settle(self, ticket: Ticket, actual_usd: float, usage: dict | None = None) -> None:
        self.inner.settle(ticket, actual_usd, usage)
        with self._lock:
            self._open.pop(ticket.id, None)
            self.spent += actual_usd

    def release(self, ticket: Ticket) -> None:
        self.inner.release(ticket)
        with self._lock:
            self._open.pop(ticket.id, None)

    def record_compute(self, job: str, seconds: float, usd: float) -> None:
        self.inner.record_compute(job, seconds, usd)

    def summary(self) -> dict:
        return self.inner.summary()


def get_ledger(backend: str | None = None) -> Ledger:
    """`TESTBED_LEDGER=local|modal`; defaults to modal inside a Modal container."""
    backend = backend or os.environ.get("TESTBED_LEDGER") or ("modal" if os.environ.get("MODAL_TASK_ID") else "local")
    if backend == "modal":
        return ModalLedger()
    if backend == "local":
        return LocalLedger()
    raise ValueError(f"unknown ledger backend {backend!r}")
