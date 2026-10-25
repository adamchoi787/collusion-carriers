"""Modal runner: one container per (card, seed, agents) job, logs on a Volume.

One-time setup (run by the user; needs a Modal login):

    .venv/bin/modal token new
    .venv/bin/modal secret create collusion-api-keys --from-dotenv .env
    .venv/bin/modal volume create collusion-runs

The Secret holds the same variable names as .env: the *_API_KEY values, the
BUDGET_USD_* caps. To change a cap, edit .env and re-run
the `secret create` line with --force.

Run, sync, report:

    .venv/bin/modal run testbed/modal_app.py::main --jobs jobs.json --concurrency 8
    .venv/bin/modal run testbed/modal_app.py::sync --prefix runs/<card_id>
    .venv/bin/python -m testbed.agents.spend --backend modal

jobs.json is a JSON (or YAML) list of jobs, for example:

    [{"card_id": "s1-calib-time", "seed": 3,
      "agents": [{"kind": "llm", "provider": "deepseek", "model": "deepseek-flash"},
                 {"kind": "llm", "provider": "deepseek", "model": "deepseek-flash"}]},
     {"card_id": "s1-calib-all", "seed": 0, "until_round": 40, "agents": [...]},
     {"config": {...engine.config_to_dict(...)...}, "checkpoint": "s1-calib-all/0.r40.ckpt.json"}]

Each job needs "card_id" (+ "study", default 1) or a full "config" dict;
"seed", "rounds" and "agents" override the card's. "until_round" stops early
and saves a checkpoint; "checkpoint" (a key from such a job, relative to
/vol/runs) branches from it with this job's config (engine.branch). Everything
engine-specific is in execute_job().

Resume: every CHECKPOINT_EVERY rounds a job saves <card_id>/<seed>.resume.ckpt.json
on the Volume (and commits it with the log so far). Re-submitting a job with the
same card_id and seed continues from that checkpoint instead of round 1, but
only if the checkpoint's config is identical to the job's; otherwise the job
starts over. Checkpointed rounds are not replayed, so their API calls are not
paid (or charged to the ledger) twice; rounds after the checkpoint are played
again. "retries" (default 1; 0 turns it off) resumes automatically, in the same
container, after a connection error or timeout. "resume": false forces a fresh
start. The resume file is deleted when the job finishes. Formation rounds that
a study's run_card plays under another card_id resume only through that
study's own checkpoints.

Open-weight models (provider "vllm") are served by testbed/serve_vllm.py; a job
with vllm agents waits until each model's endpoint answers before round 1.

API spend inside containers goes through the shared ledger (a modal.Dict), so
parallel containers can never jointly exceed BUDGET_USD_*. Container time is
recorded in the same ledger as Modal compute spend.
"""
from __future__ import annotations

import concurrent.futures as cf
import contextlib
import dataclasses
import importlib
import json
import os
import time
from pathlib import Path
from typing import Any

import modal

APP_NAME = "collusion-testbed"
SECRET_NAME = "collusion-api-keys"
VOLUME_NAME = "collusion-runs"
VOL = "/vol"                  # volume mount; logs land at /vol/runs/<card_id>/<seed>.jsonl
CPU, MEMORY_MB = 0.25, 512    # the run loop mostly waits on API latency
CHECKPOINT_EVERY = 10
VLLM_SECRET = "collusion-vllm"   # = serve_vllm.SECRET_NAME (VLLM_API_KEY for the endpoints)
# Exception class names (anywhere in the MRO) that count as infrastructure failures.
TRANSIENT = ("ConnectionError", "TimeoutError", "DeadlineExceeded", "APIConnectionError", "APITimeoutError")
ROOT = Path(__file__).resolve().parents[1]

app = modal.App(APP_NAME)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject(str(ROOT / "pyproject.toml"), optional_dependencies=["llm", "modal"])
    .env({"TESTBED_LEDGER": "modal"})
    # Keep prices.yaml and the prompt fragments (the default ignores non-.py files).
    .add_local_python_source("testbed", ignore=["**/__pycache__/**", "**/*.pyc"])
)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


# ---- pure job logic (testable without Modal) --------------------------------

def resolve_config(job: dict, engine: Any):
    """Config from job["config"] (a dict, as engine.config_to_dict writes it) or
    from job["card_id"] (+ "study", default 1) via testbed.studies.study<n>.card."""
    from testbed.types import AgentSpec

    if "config" in job:
        config = engine.config_from_dict(job["config"])
    else:
        mod = importlib.import_module(f"testbed.studies.study{job.get('study', 1)}")
        config = mod.card(job["card_id"], seed=int(job.get("seed", 0)), rounds=job.get("rounds"))
    if "seed" in job:
        config = dataclasses.replace(config, seed=int(job["seed"]))
    if job.get("rounds"):
        config = dataclasses.replace(config, rounds=int(job["rounds"]))
    if "agents" in job:
        config = dataclasses.replace(config, agents=[AgentSpec(**a) for a in job["agents"]])
    return config


def make_storage(engine: Any, runs_dir: Path, commit=None):
    """The engine's LocalStorage rooted at runs_dir; commit() also commits the
    Modal Volume, so checkpoints and finished logs are durable."""
    class VolumeStorage(engine.LocalStorage):
        def commit(self) -> None:
            if commit is not None:
                commit()

    return VolumeStorage(str(runs_dir))


def is_transient(e: BaseException) -> bool:
    return any(c.__name__ in TRANSIENT for c in type(e).__mro__) or "deadline exceeded" in str(e).lower()


def resume_path(runs_dir: Path, card_id: str, seed: int) -> Path:
    return Path(runs_dir) / card_id / f"{seed}.resume.ckpt.json"


def _json_config(engine: Any, config) -> dict:
    return json.loads(json.dumps(engine.config_to_dict(config)))


def find_resume(runs_dir: Path, config, engine: Any, last_round: int) -> tuple[dict | None, str | None]:
    """(checkpoint, None) if a resume checkpoint for this card and seed exists with
    exactly this config and fewer than last_round rounds; else (None, reason or None)."""
    path = resume_path(runs_dir, config.card_id, config.seed)
    if not path.exists():
        return None, None
    try:
        ckpt = json.loads(path.read_text())
    except (OSError, ValueError):
        return None, "resume checkpoint unreadable"
    if ckpt.get("config") != _json_config(engine, config):
        return None, "resume checkpoint has a different config"
    if not 0 < ckpt.get("round", 0) < last_round:
        return None, f"resume checkpoint at round {ckpt.get('round')} is not before round {last_round}"
    return ckpt, None


@contextlib.contextmanager
def periodic_checkpoints(engine: Any, storage: Any, every: int, saved: set):
    """Save a resume checkpoint every `every` rounds for every engine writing to
    `storage` (including the ones a study's run_card builds), committing it with
    the log so far. The engine has no per-round hook for this, so Engine.play_round
    is wrapped for the duration of the job."""
    cls = engine.Engine
    inner = cls.play_round

    def play_round(self):
        inner(self)
        if self.storage is storage and self.log and every and self.round % every == 0 \
                and self.round < self.config.rounds:
            path = resume_path(Path(storage.root), self.config.card_id, self.config.seed)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.checkpoint(), separators=(",", ":")))
            os.replace(tmp, path)          # never a half-written checkpoint
            saved.add(path)
            storage.commit()

    cls.play_round = play_round
    try:
        yield
    finally:
        cls.play_round = inner


def _old_header(log: Path) -> dict:
    try:
        with open(log) as f:
            first = json.loads(f.readline())
        return first if first.get("type") == "header" else {}
    except (OSError, ValueError):
        return {}


def wait_for_vllm(config) -> None:
    from testbed.serve_vllm import wait_ready

    for model in sorted({a.model for a in config.agents if a.kind == "llm" and a.provider == "vllm"}):
        url = next((a.params.get("base_url") for a in config.agents if a.model == model and a.params.get("base_url")),
                   None)
        wait_ready(model, url=url)


def execute_job(job: dict, runs_dir: str | Path, engine: Any = None, ledger: Any = None,
                commit=None, warm=wait_for_vllm) -> dict:
    """Run one job (see the module docstring), retrying up to job["retries"] times
    (default 1) after a transient error by resuming from the latest checkpoint.
    Records each attempt's wall time as compute spend when a ledger is given."""
    retries, errors = int(job.get("retries", 1)), []
    compute = 0.0
    while True:
        t0 = time.time()
        try:
            out = _execute_once(job, runs_dir, engine, commit, warm)
            break
        except Exception as e:
            if len(errors) >= retries or not is_transient(e):
                raise
            errors.append(f"{type(e).__name__}: {str(e)[:200]}")
        finally:
            if ledger is not None:
                from testbed.agents.budget import Prices

                seconds = time.time() - t0
                usd = Prices.load().compute_cost(seconds, CPU, MEMORY_MB / 1024)
                ledger.record_compute(f"{job.get('card_id') or job.get('config', {}).get('card_id')}/"
                                      f"{job.get('seed', '')}", seconds, usd)
                compute += usd
    if errors:
        out["retried_after"] = errors
    if ledger is not None:
        out["compute_usd"] = round(compute, 6)
    return out


def _execute_once(job: dict, runs_dir: str | Path, engine: Any, commit, warm) -> dict:
    t0 = time.time()
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    engine = engine or importlib.import_module("testbed.engine")
    config = resolve_config(job, engine)
    storage = make_storage(engine, runs_dir, commit)
    until = job.get("until_round")
    last = min(until or config.rounds, config.rounds)
    ckpt, skipped = find_resume(runs_dir, config, engine, last) if job.get("resume", True) else (None, None)
    if warm is not None and any(a.provider == "vllm" for a in config.agents):
        warm(config)
    # Study modules may define run_card (their own formation + branch) and plugins_for
    # (intervention plugins such as Study 2's monitor); without them the cell would run
    # with no intervention.
    try:
        mod = importlib.import_module(f"testbed.studies.study{config.study}")
    except ImportError:
        mod = None
    plugins = mod.plugins_for(config) if hasattr(mod, "plugins_for") else ()
    log = Path(storage.log_path(config.card_id, config.seed))
    saved: set[Path] = set()
    with periodic_checkpoints(engine, storage, int(job.get("checkpoint_every", CHECKPOINT_EVERY)), saved):
        if ckpt is not None:
            # Continue the interrupted run: same config, its own plugins, and the original
            # log header's branch info (from_checkpoint would label it a branch of itself).
            old = _old_header(log)
            eng = engine.Engine.from_checkpoint(ckpt, config, storage=storage, plugins=plugins)
            eng.branch_info = old.get("branch")
            resumed = [*old.get("resumed", []), {"from_round": ckpt["round"]}]
            header = eng._header
            eng._header = lambda: {**header(), "resumed": resumed}
            result = eng.run(until)
        elif job.get("checkpoint"):
            # A key returned by an earlier until_round job, absolute or relative to runs_dir.
            key = job["checkpoint"]
            key = key if Path(key).is_absolute() else str(runs_dir / key)
            result = engine.branch(key, config, storage=storage, until_round=until, plugins=plugins)
        elif hasattr(mod, "run_card"):
            result = mod.run_card(config, storage=storage, until_round=until)
        else:
            result = engine.run(config, storage=storage, until_round=until, plugins=plugins)
    # Finished: the resume files are spent (a later re-submit starts over).
    for path in saved | {resume_path(runs_dir, config.card_id, config.seed)}:
        path.unlink(missing_ok=True)
    storage.commit()
    seconds = time.time() - t0
    out = {"card_id": config.card_id, "seed": config.seed, "seconds": round(seconds, 2),
           "log": str(log), "log_bytes": log.stat().st_size if log.exists() else None,
           "rounds": len({r["round"] for r in getattr(result, "records", [])}),
           "checkpoint": getattr(result, "checkpoint_key", None)}
    if ckpt is not None:
        out["resumed_from_round"] = ckpt["round"]
    if skipped:
        out["resume_skipped"] = skipped
    return out


def sync_logs(vol: Any, prefix: str, dest: str | Path) -> list[str]:
    """Download files under `prefix` on the volume into `dest`, skipping files
    already present with the same size. Volume paths mirror runs/<card>/<seed>.jsonl."""
    dest = Path(dest)
    got = []
    for entry in vol.listdir(prefix, recursive=True):
        if getattr(entry.type, "name", entry.type) != "FILE":
            continue
        rel = Path(entry.path)
        if rel.parts and rel.parts[0] == "runs":
            rel = Path(*rel.parts[1:])
        target = dest / rel
        if target.exists() and target.stat().st_size == entry.size:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            for chunk in vol.read_file(entry.path):
                f.write(chunk)
        got.append(str(target))
    return got


def load_jobs(path: str) -> list[dict]:
    text = Path(path).read_text()
    if path.endswith((".yaml", ".yml")):
        import yaml

        return yaml.safe_load(text)
    return json.loads(text)


# ---- Modal functions and entrypoints ------------------------------------------

@app.function(image=image, secrets=[modal.Secret.from_name(SECRET_NAME), modal.Secret.from_name(VLLM_SECRET)],
              volumes={VOL: volume}, cpu=CPU, memory=MEMORY_MB, timeout=4 * 3600, max_containers=200, retries=0)
def run_job(job: dict) -> dict:
    # retries=0 at the Modal level: a fresh container would replay the run from its last
    # checkpoint only; execute_job already resumes in place after transient errors.
    from testbed.agents.budget import get_ledger

    os.chdir(VOL)  # checkpoint keys are absolute paths under /vol/runs
    try:
        return execute_job(job, runs_dir=f"{VOL}/runs", ledger=get_ledger("modal"), commit=volume.commit)
    finally:
        volume.commit()


@app.local_entrypoint()
def main(jobs: str, concurrency: int = 8):
    """Fan the jobs out, at most `concurrency` containers at a time."""
    todo = load_jobs(jobs)
    print(f"{len(todo)} jobs, concurrency {concurrency}")
    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(run_job.remote, j): j for j in todo}
        for fut in cf.as_completed(futures):
            j = futures[fut]
            try:
                print(json.dumps(fut.result()))
            except Exception as e:  # noqa: BLE001 - report and keep going
                print(json.dumps({"failed": j.get("card_id") or j.get("config", {}).get("card_id"),
                                  "seed": j.get("seed"), "error": f"{type(e).__name__}: {str(e)[:300]}"}))


@app.local_entrypoint()
def sync(prefix: str = "runs", dest: str = "runs"):
    """Download logs from the Volume for analysis (skips files already here)."""
    got = sync_logs(volume, prefix, dest)
    print(f"downloaded {len(got)} file(s) into {dest}/")


@app.local_entrypoint()
def spend():
    """API spend and Modal compute from the shared ledger."""
    from testbed.agents.budget import get_ledger
    from testbed.agents.spend import report

    ledger = get_ledger("modal")
    print(report(ledger.summary(), ledger.caps))
