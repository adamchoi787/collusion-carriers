"""Open-weight models on Modal GPUs, served by vLLM's OpenAI-compatible server.

One web endpoint per model, each on its own GPU type. Weights are downloaded
once into the Modal Volume `collusion-models` (never onto the Mac) and loaded
from there. Containers scale to zero after SCALEDOWN_S idle seconds, and at
most MAX_CONTAINERS run per model.

One-time setup (needs a Modal login):

    # A random endpoint key that never appears on screen. Agents on Modal read the
    # same Secret. To call the endpoint from the Mac too, recreate the Secret (--force)
    # from a value you also put in .env as VLLM_API_KEY.
    f=$(mktemp) && .venv/bin/python -c "import secrets; print('VLLM_API_KEY=' + secrets.token_urlsafe(32))" \\
        > "$f" && .venv/bin/modal secret create collusion-vllm --from-dotenv "$f"; rm -f "$f"
    .venv/bin/modal run testbed/serve_vllm.py::download --model qwen     # weights -> Volume (CPU only)
    .venv/bin/modal run testbed/serve_vllm.py::download --model gemma

Serve, use, stop:

    .venv/bin/modal deploy testbed/serve_vllm.py       # endpoints idle at zero until called
    # agents: {"kind": "llm", "provider": "vllm", "model": "Qwen/Qwen3.8-27B-FP8", "reasoning": "off"}
    .venv/bin/modal app stop collusion-vllm            # stop GPUs and endpoints entirely

The vllm provider finds an endpoint from VLLM_BASE_URL if set, else by
looking the function up in this app (endpoint_url below). GPU time is recorded
in the shared ledger as Modal compute (job "gpu:<key>"), priced from
prices.yaml, every HEARTBEAT_S seconds while a container is up.

Sampling: requests carry no temperature/top_p/top_k, so vLLM applies the
model's own generation_config.json (`--generation-config auto`). Each request
carries a seed derived from (run seed, round, firm, phase), see llm.call_seed.
BATCH_INVARIANT turns on vLLM's batch-invariant kernels (beta), so the same
seed gives the same tokens however requests are batched.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import modal

APP_NAME = "collusion-vllm"
SECRET_NAME = "collusion-vllm"            # VLLM_API_KEY, shared with the agent containers
MODELS_VOLUME = "collusion-models"
MODELS_DIR = "/models"                    # volume mount: /models/<repo id>, /models/vllm-cache
VLLM_VERSION = "0.31.0"                   # released 5 Oct 2026
PORT = 8000
SCALEDOWN_S = 240                         # idle seconds before a GPU container stops
MAX_CONTAINERS = 1
STARTUP_TIMEOUT_S = 20 * 60               # first start compiles kernels; later starts hit the cache
MAX_INPUTS = 64                           # concurrent requests per container (vLLM batches them)
HEARTBEAT_S = 60
CPU_CORES, MEMORY_MB = 2.0, 16384        # billed on top of the GPU (Modal bills max(request, use))
BATCH_INVARIANT = True


@dataclass(frozen=True)
class ServedModel:
    key: str                  # function name and ledger label
    repo: str                 # Hugging Face repo id, also the served model name
    gpu: str                  # Modal GPU type (priced in prices.yaml modal.gpu_second)
    max_model_len: int
    reasoning_parser: str
    args: tuple[str, ...] = field(default=())


# Two current open-weight instruct models from different labs (choice: 24 Oct 2026).
MODELS = {
    "qwen": ServedModel(
        key="qwen", repo="Qwen/Qwen3.8-27B-FP8", gpu="L40S", max_model_len=65536, reasoning_parser="qwen3",
        # Official FP8 checkpoint (31 GB). Hybrid attention (16 of 64 layers keep a KV cache),
        # so the 48 GB L40S leaves room for well over 100k cached tokens.
        args=("--language-model-only",)),
    "gemma": ServedModel(
        key="gemma", repo="google/gemma-4-26B-A4B-it", gpu="A100-80GB", max_model_len=65536,
        reasoning_parser="gemma4",
        # BF16 as released (52 GB), so no on-the-fly quantisation changes the model.
        args=("--language-model-only",)),
}
BY_REPO = {m.repo: m for m in MODELS.values()}


def serve_command(m: ServedModel) -> list[str]:
    """The key is never on the command line: vLLM reads VLLM_API_KEY from the
    environment (set by the Modal Secret) and then requires it on every request."""
    cmd = ["vllm", "serve", f"{MODELS_DIR}/{m.repo}", "--served-model-name", m.repo,
           "--host", "0.0.0.0", "--port", str(PORT),
           "--max-model-len", str(m.max_model_len), "--enable-prefix-caching",
           "--generation-config", "auto", "--reasoning-parser", m.reasoning_parser,
           "--enable-prompt-tokens-details", "--gpu-memory-utilization", "0.92", *m.args]
    return cmd


def endpoint_url(model: str) -> str:
    """OpenAI base URL (".../v1") of the deployed endpoint serving `model` (a repo id)."""
    m = BY_REPO.get(model)
    if m is None:
        raise ValueError(f"{model!r} is not served by {APP_NAME}; known: {sorted(BY_REPO)}")
    return modal.Function.from_name(APP_NAME, m.key).get_web_url().rstrip("/") + "/v1"


def wait_ready(model: str, url: str | None = None, timeout_s: float = STARTUP_TIMEOUT_S) -> float:
    """Block until the endpoint lists `model` (a cold start loads weights and compiles);
    return the seconds waited. Uses VLLM_BASE_URL / VLLM_API_KEY like the provider."""
    import json
    import urllib.error
    import urllib.request

    base = (url or os.environ.get("VLLM_BASE_URL", "").strip() or endpoint_url(model)).rstrip("/")
    key = os.environ.get("VLLM_API_KEY", "").strip()
    req = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {key}"} if key else {})
    t0 = time.time()
    while True:
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if any(m.get("id") == model for m in json.load(r).get("data", [])):
                    return time.time() - t0
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError(f"{base}: {e.code}; VLLM_API_KEY does not match the endpoint's") from None
        except (OSError, ValueError):     # not up yet (URLError and timeouts are OSErrors)
            pass
        if time.time() - t0 > timeout_s:
            raise TimeoutError(f"{base} did not serve {model} within {timeout_s:.0f} s")
        time.sleep(5)


# ---- Modal app ----------------------------------------------------------------

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(MODELS_VOLUME, create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(f"vllm=={VLLM_VERSION}", "pyyaml", "python-dotenv")
    .env({"VLLM_CACHE_ROOT": f"{MODELS_DIR}/vllm-cache",
          "VLLM_BATCH_INVARIANT": "1" if BATCH_INVARIANT else "0", "TESTBED_LEDGER": "modal"})
    .add_local_python_source("testbed", ignore=["**/__pycache__/**", "**/*.pyc"])
)


def _heartbeat(m: ServedModel) -> None:
    """Record this container's GPU time in the shared ledger, HEARTBEAT_S at a time,
    so a killed container loses at most one interval."""
    from testbed.agents.budget import Caps, ModalLedger, Prices

    ledger, prices = ModalLedger(caps=Caps()), Prices.load()
    last = time.time()
    while True:
        time.sleep(HEARTBEAT_S)
        now = time.time()
        try:
            usd = prices.gpu_cost(now - last, m.gpu, CPU_CORES, MEMORY_MB / 1024)
            ledger.record_compute(f"gpu:{m.key}", now - last, usd, gpu=m.gpu)
            last = now
        except Exception as e:  # noqa: BLE001 - keep serving; the next beat retries
            print(f"ledger heartbeat failed: {type(e).__name__}: {e}")


def _start(key: str) -> None:
    m = MODELS[key]
    if not Path(f"{MODELS_DIR}/{m.repo}/config.json").exists():
        raise RuntimeError(f"weights missing: run `modal run testbed/serve_vllm.py::download --model {key}`")
    if not os.environ.get("VLLM_API_KEY"):
        raise RuntimeError(f"VLLM_API_KEY missing: create the Modal Secret {SECRET_NAME} (see the docstring)")
    threading.Thread(target=_heartbeat, args=(m,), daemon=True).start()
    proc = subprocess.Popen(serve_command(m))

    def watch():
        # If vLLM dies (bad flag, out of memory), end the container now instead of
        # holding the GPU until the startup timeout.
        code = proc.wait()
        print(f"vllm exited with {code}; stopping the container")
        os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


_serve = dict(image=image, volumes={MODELS_DIR: volume}, secrets=[modal.Secret.from_name(SECRET_NAME)],
              cpu=CPU_CORES, memory=MEMORY_MB, scaledown_window=SCALEDOWN_S, max_containers=MAX_CONTAINERS,
              timeout=3600)


@app.function(gpu=MODELS["qwen"].gpu, **_serve)
@modal.concurrent(max_inputs=MAX_INPUTS)
@modal.web_server(port=PORT, startup_timeout=STARTUP_TIMEOUT_S)
def qwen():
    _start("qwen")


@app.function(gpu=MODELS["gemma"].gpu, **_serve)
@modal.concurrent(max_inputs=MAX_INPUTS)
@modal.web_server(port=PORT, startup_timeout=STARTUP_TIMEOUT_S)
def gemma():
    _start("gemma")


# The download is its own app, so it registers no GPU function and runs on CPU only.
downloader = modal.App(APP_NAME + "-download")


@downloader.function(image=image, volumes={MODELS_DIR: volume}, cpu=4, memory=8192, timeout=3 * 3600)
def download_weights(key: str) -> str:
    from huggingface_hub import snapshot_download

    m = MODELS[key]
    path = snapshot_download(m.repo, local_dir=f"{MODELS_DIR}/{m.repo}",
                             ignore_patterns=["*.pt", "*.bin", "original/*"])
    volume.commit()
    size = sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file())
    return f"{m.repo}: {size / 1e9:.1f} GB in {MODELS_VOLUME}:{m.repo}"


@downloader.local_entrypoint()
def download(model: str = "qwen"):
    """Download weights into the Volume (runs on a Modal CPU container)."""
    print(download_weights.remote(model))
