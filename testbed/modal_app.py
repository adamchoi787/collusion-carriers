"""Modal runner: one container per (card, seed, agents) job, logs on a Volume.

One-time setup (run by the user; needs a Modal login):

    .venv/bin/modal token new
    .venv/bin/modal secret create collusion-api-keys --from-dotenv .env
    .venv/bin/modal volume create collusion-runs

The Secret holds the same variable names as .env: the *_API_KEY values, the
BUDGET_USD_* caps. To change a cap, edit .env and re-run
the `secret create` line with --force.

Run, sync, report:

    .venv/bin/modal run testbed/modal_app.py --jobs jobs.json --concurrency 8
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

API spend inside containers goes through the shared ledger (a modal.Dict), so
parallel containers can never jointly exceed BUDGET_USD_*. Container time is
recorded in the same ledger as Modal compute spend.
"""
from __future__ import annotations

import concurrent.futures as cf
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


def execute_job(job: dict, runs_dir: str | Path, engine: Any = None, ledger: Any = None,
                commit=None) -> dict:
    """Run one job through engine.run / engine.branch, logging under runs_dir
    (runs_dir/<card_id>/<seed>.jsonl). Records the job's wall time as compute
    spend when a ledger is given."""
    t0 = time.time()
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    engine = engine or importlib.import_module("testbed.engine")
    config = resolve_config(job, engine)
    storage = make_storage(engine, runs_dir, commit)
    until = job.get("until_round")
    # Study modules may define run_card (their own formation + branch) and plugins_for
    # (intervention plugins such as Study 2's monitor); without them the cell would run
    # with no intervention.
    try:
        mod = importlib.import_module(f"testbed.studies.study{config.study}")
    except ImportError:
        mod = None
    plugins = mod.plugins_for(config) if hasattr(mod, "plugins_for") else ()
    if job.get("checkpoint"):
        # A key returned by an earlier until_round job, absolute or relative to runs_dir.
        key = job["checkpoint"]
        key = key if Path(key).is_absolute() else str(runs_dir / key)
        result = engine.branch(key, config, storage=storage, until_round=until, plugins=plugins)
    elif hasattr(mod, "run_card"):
        result = mod.run_card(config, storage=storage, until_round=until)
    else:
        result = engine.run(config, storage=storage, until_round=until, plugins=plugins)
    storage.commit()
    log = Path(storage.log_path(config.card_id, config.seed))
    seconds = time.time() - t0
    out = {"card_id": config.card_id, "seed": config.seed, "seconds": round(seconds, 2),
           "log": str(log), "log_bytes": log.stat().st_size if log.exists() else None,
           "rounds": len({r["round"] for r in getattr(result, "records", [])}),
           "checkpoint": getattr(result, "checkpoint_key", None)}
    if ledger is not None:
        from testbed.agents.budget import Prices

        usd = Prices.load().compute_cost(seconds, CPU, MEMORY_MB / 1024)
        ledger.record_compute(f"{config.card_id}/{config.seed}", seconds, usd)
        out["compute_usd"] = round(usd, 6)
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

@app.function(image=image, secrets=[modal.Secret.from_name(SECRET_NAME)], volumes={VOL: volume},
              cpu=CPU, memory=MEMORY_MB, timeout=4 * 3600, max_containers=50, retries=0)
def run_job(job: dict) -> dict:
    # retries=0: a retried job would pay for its API calls twice.
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
