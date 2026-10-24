"""The repeated procurement game.

Round r, for every firm i (all phases simultaneous):
    draw     costs and z from default_rng([seed, r, i])                       (rng.draw)
    chat     only with free chat
    prebid   one symbol per medium (invalid or missing: the cover default), plus any private message
    shown    each rival's pre-bid as the observer sees it (delivered / scrambled / "unavailable" / absent)
    bid      one sealed bid per contract (None = no bid)
    reveal   per contract, the lowest bid <= reserve wins at its bid; ties by the seeded RNG
    probe    belief probes due this round
    log      one record per firm (the contract's JSONL format)

Use `run(config, ...)` and `branch(checkpoint, new_config, ...)`; `Engine` is the
object plugins receive.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

import numpy as np

from ..types import MEDIA, Action, AgentSpec, Config, Observation
from . import cover, rng
from .config import (PRIVATE_MESSAGE, config_from_dict, config_to_dict, effective_visibility,
                     private_message_available, validate)
from .factory import Agent, make_agent, spec_label
from .framing import framing
from .plugins import Plugin, SwapPlugin
from .storage import LocalStorage, LogSink, Storage, dumps

CHECKPOINT_VERSION = 1
UNAVAILABLE = "unavailable"


def _jsonable(x):
    return json.loads(dumps(x))


@dataclass
class RunResult:
    config: Config = dataclasses.field(repr=False)
    records: list[dict] = dataclasses.field(repr=False)   # every round record, incl. copied pre-branch rounds
    engine: "Engine" = dataclasses.field(repr=False)
    checkpoint: dict | None = dataclasses.field(default=None, repr=False)  # set when stopped at until_round
    checkpoint_key: str | None = None   # storage key of the saved checkpoint

    def __repr__(self) -> str:
        return (f"RunResult(card_id={self.config.card_id!r}, seed={self.config.seed}, "
                f"rounds={self.engine.round}, checkpoint_key={self.checkpoint_key!r})")


class Engine:
    def __init__(self, config: Config, agents: Sequence[Agent] | None = None, *,
                 storage: Storage | None = None, plugins: Sequence[Plugin] = (),
                 agent_factory: Callable = make_agent, log: bool = True):
        validate(config)
        self.config = config
        self.storage = storage if storage is not None else LocalStorage()
        self.log = log
        self.agent_factory = agent_factory
        self.plugins: list[Plugin] = list(plugins)
        if config.identity.swap is not None and not any(p.name == SwapPlugin.name for p in self.plugins):
            self.plugins.append(SwapPlugin())
        n = config.n_firms
        if agents is not None:
            if len(agents) != n:
                raise ValueError(f"{len(agents)} agents for {n} firms")
            self.agents = list(agents)
            self.agent_specs: list[AgentSpec | None] = [None] * n
        else:
            if not config.agents:
                raise ValueError("no agents: pass agents=... or set config.agents")
            specs = config.agents if len(config.agents) == n else config.agents * n
            self.agent_specs = list(specs)
            self.agents = [self.make_agent(s, i) for i, s in enumerate(specs)]
        self.agent_versions = [1] * n
        self.agent_labels = [f"{spec_label(s)}#1" for s in self.agent_specs]
        # run state (everything below goes into checkpoints)
        self.round = 0                                        # last completed round
        self.round_now = 0                                    # round being played
        self.actual_prebids: list[list[dict[str, int]]] = [[] for _ in range(n)]  # [firm][round-1]
        self.pm_log: list[list[list]] = [[] for _ in range(n)]  # [sender] -> [round, to, text]
        self.histories: list[list[dict]] = [[] for _ in range(n)]
        self.records: list[dict] = []
        self.fines_total = [0.0] * n
        self.branch_info: dict | None = None
        # current-round scratch, readable by plugins
        self.costs: list[list[int]] = []
        self.z: list[int] = []
        self.defaults: list[dict[str, int]] = []
        self._cur: list[dict] = []
        self._sink: LogSink | None = None
        self._rules = {"n_firms": n, "k_contracts": config.k_contracts, "reserve": config.reserve,
                       "cost_low": config.cost_low, "cost_high": config.cost_high,
                       "z_levels": config.z_levels, "symbols": dict(config.symbols), "rounds": config.rounds}
        self._started = False

    # ---- helpers for plugins ------------------------------------------------

    def make_agent(self, spec: AgentSpec, firm: int) -> Agent:
        return self.agent_factory(spec, firm, self.config)

    def swap_agent(self, firm: int, new_agent: Agent, *, wipe_memory: bool = False,
                   spec: AgentSpec | None = None) -> None:
        """Replace the agent playing `firm` from now on. The firm index (its displayed identity)
        is unchanged. Unless `wipe_memory`, the new agent is restored from the old one's snapshot."""
        if not wipe_memory:
            new_agent.restore(self.agents[firm].snapshot())
        self.agents[firm] = new_agent
        self.agent_specs[firm] = spec
        self.agent_versions[firm] += 1
        self.agent_labels[firm] = f"{spec_label(spec)}#{self.agent_versions[firm]}"

    def add_fine(self, firm: int, amount: float, reason: str | None = None) -> None:
        """Fine `firm` in the current round (shows in its record and in later Observation.fines)."""
        self._cur[firm]["fine"] += float(amount)
        self.fines_total[firm] += float(amount)
        if reason:
            self._cur[firm]["flags"].append(f"fine:{reason}")

    def add_flag(self, firm: int, flag: str) -> None:
        self._cur[firm]["flags"].append(flag)

    # ---- the loop -------------------------------------------------------------

    def run(self, until_round: int | None = None) -> RunResult:
        last = self.config.rounds if until_round is None else min(until_round, self.config.rounds)
        if not self._started:
            self._start()
        try:
            while self.round < last:
                self.play_round()
        finally:
            if self._sink is not None:
                self._sink.close()
                self._sink = None
            if self.log:
                self.storage.commit()
        result = RunResult(self.config, self.records, self)
        if self.round < self.config.rounds:
            result.checkpoint = self.checkpoint()
            if self.log:
                result.checkpoint_key = self.storage.save_checkpoint(
                    self.config.card_id, self.config.seed, self.round, result.checkpoint)
                self.storage.commit()
        return result

    def _start(self) -> None:
        self._started = True
        if self.log:
            self._sink = self.storage.open_log(self.config.card_id, self.config.seed)
            self._sink.write(self._header())
            for rec in self.records:            # pre-branch rounds, so each log is self-contained
                self._sink.write(rec)
        for p in self.plugins:
            p.on_run_start(self)

    def _header(self) -> dict:
        h = {"type": "header", "config": config_to_dict(self.config), "git_sha": git_sha(),
             "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "card_id": self.config.card_id, "seed": self.config.seed,
             "visibility_effective": effective_visibility(self.config),
             "agents": list(self.agent_labels)}
        if self.branch_info:
            h["branch"] = self.branch_info
        return h

    def _obs(self, i: int, phase: str, **kw) -> Observation:
        obs = Observation(firm=i, round=self.round_now, phase=phase, costs=list(self.costs[i]),
                          z=self.z[i], defaults=dict(self.defaults[i]),
                          framing=framing(self.config, i, self.round_now),
                          history=list(self.histories[i]), fines=self.fines_total[i],
                          rules=dict(self._rules), **kw)
        for p in self.plugins:
            obs = p.transform_observation(self, obs)
        return obs

    def _act(self, i: int, obs: Observation, usage: dict, key: str) -> Action:
        a = self.agents[i].act(obs) or Action()
        if a.usage:
            usage[key] = a.usage
        return a

    def play_round(self) -> None:
        cfg = self.config
        n, k = cfg.n_firms, cfg.k_contracts
        r = self.round_now = self.round + 1
        draws = [rng.draw(cfg.seed, r, i, k, cfg.cost_low, cfg.cost_high, cfg.z_levels) for i in range(n)]
        self.costs = [c for c, _ in draws]
        self.z = [z for _, z in draws]
        self.defaults = [cover.defaults(z, cfg.symbols, cfg.z_levels) for z in self.z]
        self._cur = [{"fine": 0.0, "flags": []} for _ in range(n)]
        for p in self.plugins:
            p.on_round_start(self, r)
        usage: list[dict] = [{} for _ in range(n)]
        vis = effective_visibility(cfg)

        # chat (free chat only); private messages may be sent here or with the pre-bid
        sent: list[list[dict]] = [[] for _ in range(n)]
        received: list[list[dict]] = [[] for _ in range(n)]
        if cfg.free_chat:
            obs = [self._obs(i, "chat") for i in range(n)]
            actions = [self._act(i, obs[i], usage[i], "chat") for i in range(n)]
            self._messages(r, actions, vis, sent, received)

        # prebid; private messages sent now reach rivals before they bid
        obs = [self._obs(i, "prebid", messages=list(received[i])) for i in range(n)]
        actions = [self._act(i, obs[i], usage[i], "prebid") for i in range(n)]
        prebids = [self._valid_prebid(i, a.prebid) for i, a in enumerate(actions)]
        self._messages(r, actions, vis, sent, received)
        for p in self.plugins:
            p.on_prebids(self, r, prebids)
        public = [self._public_log(vis, r, i, prebids[i]) for i in range(n)]
        for i in range(n):
            self.actual_prebids[i].append(dict(prebids[i]))
        shown = {o: {j: dict(public[j]) for j in range(n) if j != o} for o in range(n)}
        for p in self.plugins:
            shown = p.transform_shown(self, r, shown)

        # bid
        obs = [self._obs(i, "bid", rivals_prebid=shown[i], messages=list(received[i])) for i in range(n)]
        actions = [self._act(i, obs[i], usage[i], "bid") for i in range(n)]
        bids = [self._valid_bids(i, a.bids) for i, a in enumerate(actions)]
        for p in self.plugins:
            bids = p.on_bids(self, r, bids)

        # reveal
        winners, prices = [], []
        for c in range(k):
            offers = [(bids[i][c], i) for i in range(n) if bids[i][c] is not None and bids[i][c] <= cfg.reserve]
            if not offers:
                winners.append(None)
                prices.append(None)
                continue
            low = min(b for b, _ in offers)
            tied = [i for b, i in offers if b == low]
            winners.append(tied[0] if len(tied) == 1 else tied[rng.tie_break(cfg.seed, r, c, len(tied))])
            prices.append(low)
        profit = [sum(prices[c] - self.costs[i][c] for c in range(k) if winners[c] == i) for i in range(n)]
        for i in range(n):
            log = [dict(prebids[i]) if j == i else dict(shown[i].get(j, {})) for j in range(n)]
            self.histories[i].append(_jsonable({
                "round": r, "log": log, "bids": [list(b) for b in bids], "winner": winners,
                "price": prices, "own_costs": self.costs[i], "own_profit": profit[i],
                "messages": received[i]}))

        # probe
        answers: list[dict | None] = [None] * n
        for pr in cfg.probes:
            if not (r in pr.rounds or (pr.every and r % pr.every == 0)):
                continue
            for i in (range(n) if pr.firms is None else pr.firms):
                o = self._obs(i, "probe", rivals_prebid=shown[i], messages=list(received[i]),
                              probe=pr.question, probe_id=pr.id)
                a = self._act(i, o, usage[i], f"probe:{pr.id}")
                answers[i] = {**(answers[i] or {}), pr.id: a.answer}

        records = [{
            "type": "round", "round": r, "firm": i, "z": self.z[i], "costs": self.costs[i],
            "defaults": self.defaults[i], "prebid": prebids[i],
            "shown": {str(j): v for j, v in shown[i].items()},
            "messages_sent": sent[i], "bids": bids[i], "won": [w == i for w in winners],
            "price": prices, "profit": profit[i], "fine": 0.0, "flags": [], "probe": answers[i],
            "usage": usage[i],
            # additive fields beyond the contract
            "card_id": cfg.card_id, "seed": cfg.seed, "agent": self.agent_labels[i],
            "messages_received": received[i], "winner": winners,
        } for i in range(n)]
        for p in self.plugins:
            p.on_round_end(self, r, records)
        for i, rec in enumerate(records):
            rec["fine"] = self._cur[i]["fine"]
            rec["flags"] = list(self._cur[i]["flags"])
            rec = _jsonable(rec)
            self.records.append(rec)
            if self._sink is not None:
                self._sink.write(rec)
        self.round = r

    def _messages(self, r: int, actions: list[Action], vis: dict, sent: list[list[dict]],
                  received: list[list[dict]]) -> None:
        """Deliver this phase's chat (if free chat) and private messages, applying decoys."""
        n = self.config.n_firms
        deliveries, new_pm = [], []
        for i, a in enumerate(actions):
            if a.chat:
                sent[i].append({"channel": "chat", "text": str(a.chat)})
                if self.config.free_chat:
                    deliveries += [{"to": j, "from": i, "channel": "chat", "text": str(a.chat)}
                                   for j in range(n) if j != i]
            pms = a.private_message
            for pm in ([pms] if isinstance(pms, dict) else pms or []):
                to, text = pm.get("to"), str(pm.get("text", ""))
                if not isinstance(to, int) or isinstance(to, bool) or not 0 <= to < n or to == i:
                    self.add_flag(i, "invalid_private_message")
                    continue
                sent[i].append({"channel": PRIVATE_MESSAGE, "to": to, "text": text})
                if private_message_available(self.config):
                    deliveries += self._deliver_pm(vis[PRIVATE_MESSAGE], r, i, to, text)
                new_pm.append((i, [r, to, text]))
        for i, entry in new_pm:          # logged after delivery: scrambles draw from earlier rounds only
            self.pm_log[i].append(entry)
        for p in self.plugins:
            deliveries = p.transform_messages(self, r, deliveries)
        for d in deliveries:
            received[d["to"]].append({key: v for key, v in d.items() if key != "to"})

    # ---- visibility and decoys -----------------------------------------------

    def _public_log(self, vis: dict, r: int, i: int, prebid: dict[str, int]) -> dict:
        """Firm i's entry in the public activity log, as every rival sees it."""
        out: dict[str, int | str] = {}
        for mi, m in enumerate(MEDIA):
            v = vis[m]
            if v == "delivered":
                out[m] = prebid[m]
            elif v == "scrambled":
                if r == 1:
                    out[m] = self.defaults[i][m]
                else:
                    earlier = rng.scramble_round(self.config.seed, r, i, mi, r - 1)
                    out[m] = self.actual_prebids[i][earlier - 1][m]
            elif v == "error":
                out[m] = UNAVAILABLE
        return out

    def _deliver_pm(self, vis: str, r: int, i: int, to: int, text: str) -> list[dict]:
        base = {"to": to, "from": i, "channel": PRIVATE_MESSAGE}
        if vis == "delivered":
            return [{**base, "text": text}]
        if vis == "error":
            return [{**base, "text": UNAVAILABLE}]
        if vis == "scrambled":
            earlier = [t for (rr, j, t) in self.pm_log[i] if j == to and rr < r]
            if earlier:
                return [{**base, "text": earlier[rng.scramble_message(self.config.seed, r, i, to, len(earlier))]}]
        return []

    # ---- validation -------------------------------------------------------------

    def _valid_prebid(self, i: int, prebid: dict | None) -> dict[str, int]:
        if prebid is None:
            self.add_flag(i, "no_prebid")
            return dict(self.defaults[i])
        out = {}
        for m in MEDIA:
            v = prebid.get(m)
            ok = _as_int(v)
            if ok is None or not 0 <= ok < self.config.symbols[m]:
                self.add_flag(i, f"invalid_prebid:{m}")
                ok = self.defaults[i][m]
            out[m] = ok
        return out

    def _valid_bids(self, i: int, bids: list | None) -> list[float | None]:
        k = self.config.k_contracts
        if bids is None:
            return [None] * k
        if len(bids) != k:
            self.add_flag(i, "bad_bid_count")
        out: list[float | None] = []
        for c in range(k):
            b = bids[c] if c < len(bids) else None
            if b is None:
                out.append(None)
                continue
            try:
                f = float(b)
            except (TypeError, ValueError):
                f = math.nan
            if not math.isfinite(f) or f < 0:
                self.add_flag(i, f"invalid_bid:{c}")
                out.append(None)
            else:
                out.append(int(f) if f.is_integer() else f)
        return out

    # ---- checkpoints ---------------------------------------------------------------

    def checkpoint(self) -> dict:
        """JSON-serialisable state after self.round, plus agent snapshots and plugin state."""
        return _jsonable({
            "version": CHECKPOINT_VERSION, "config": config_to_dict(self.config), "round": self.round,
            "state": {
                "actual_prebids": self.actual_prebids, "pm_log": self.pm_log,
                "histories": self.histories, "records": self.records, "fines_total": self.fines_total,
                "agent_specs": [None if s is None else dataclasses.asdict(s) for s in self.agent_specs],
                "agent_labels": self.agent_labels, "agent_versions": self.agent_versions,
            },
            "agents": [a.snapshot() for a in self.agents],
            "plugins": {p.name: p.state_dict() for p in self.plugins},
        })

    @classmethod
    def from_checkpoint(cls, ckpt: dict, new_config: Config | None = None,
                        agents: Sequence[Agent] | None = None, **kw) -> "Engine":
        old = config_from_dict(ckpt["config"])
        cfg = new_config or old
        for f in ("seed", "n_firms", "k_contracts", "cost_low", "cost_high", "z_levels"):
            if getattr(cfg, f) != getattr(old, f):
                raise ValueError(f"branch must keep {f} ({getattr(old, f)} != {getattr(cfg, f)})")
        st = ckpt["state"]
        specs = [None if s is None else _spec_from_dict(s) for s in st["agent_specs"]]
        if agents is None:
            if any(s is None for s in specs):
                raise ValueError("checkpoint agents were passed as objects; pass agents=... to branch")
            factory = kw.get("agent_factory", make_agent)
            agents = [factory(s, i, cfg) for i, s in enumerate(specs)]
        eng = cls(cfg, agents, **kw)
        eng.agent_specs = specs
        eng.agent_labels = list(st["agent_labels"])
        eng.agent_versions = list(st["agent_versions"])
        for a, snap in zip(eng.agents, ckpt["agents"]):
            a.restore(snap)
        eng.round = ckpt["round"]
        eng.actual_prebids = st["actual_prebids"]
        eng.pm_log = st["pm_log"]
        eng.histories = st["histories"]
        eng.records = st["records"]
        eng.fines_total = st["fines_total"]
        eng.branch_info = {"from_card": old.card_id, "from_round": ckpt["round"]}
        states = ckpt.get("plugins", {})
        for p in eng.plugins:
            if p.name in states:
                p.load_state_dict(states[p.name])
        return eng


def _spec_from_dict(d: dict) -> AgentSpec:
    return AgentSpec(**d)


def _as_int(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return int(v)
    return None


_GIT_SHA: list = []


def git_sha() -> str | None:
    if os.environ.get("GIT_SHA"):
        return os.environ["GIT_SHA"]
    if not _GIT_SHA:
        try:
            out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
                                 cwd=os.path.dirname(os.path.abspath(__file__)))
            _GIT_SHA.append((out.stdout.strip() or None) if out.returncode == 0 else None)
        except (OSError, subprocess.SubprocessError):
            _GIT_SHA.append(None)
    return _GIT_SHA[0]


# ---- entry points -------------------------------------------------------------------

def run(config: Config, agents: Sequence[Agent] | None = None, *, until_round: int | None = None,
        storage: Storage | None = None, plugins: Sequence[Plugin] = (),
        agent_factory: Callable = make_agent, log: bool = True) -> RunResult:
    """Play `config` from round 1. With `until_round=r`, stop after round r and return
    (and save to storage) a checkpoint that `branch` can resume from."""
    eng = Engine(config, agents, storage=storage, plugins=plugins, agent_factory=agent_factory, log=log)
    return eng.run(until_round)


def branch(checkpoint: dict | str, new_config: Config | None = None, agents: Sequence[Agent] | None = None, *,
           until_round: int | None = None, storage: Storage | None = None, plugins: Sequence[Plugin] = (),
           agent_factory: Callable = make_agent, log: bool = True) -> RunResult:
    """Resume a checkpoint (a dict, or a key/path for storage.load_checkpoint) at round r+1
    under `new_config` (same seed, firms and cost model).

    The agents playing at the checkpoint continue (rebuilt from their specs, or `agents`)
    and are restored from their snapshots. The new log, under new_config.card_id, repeats
    the pre-branch records after its header, so every log file is self-contained."""
    if isinstance(checkpoint, str):
        checkpoint = (storage if storage is not None else LocalStorage()).load_checkpoint(checkpoint)
    eng = Engine.from_checkpoint(checkpoint, new_config, agents, storage=storage, plugins=plugins,
                                 agent_factory=agent_factory, log=log)
    return eng.run(until_round)
