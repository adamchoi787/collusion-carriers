# Testbed contract

How the components fit together. [`plan/research-plan.md`](../plan/research-plan.md) §3 is the design; this file is the build contract. Shared types live in [`types.py`](types.py).

## Layout and ownership

| Path | Owner | What |
|---|---|---|
| `testbed/types.py`, this file | coordinator | Shared types. Components may add optional fields with defaults; never rename or remove fields |
| `testbed/engine/` | **core-engine** | Game loop, media, cover defaults, visibility and decoys, chat and `private_message`, belief probes, checkpoints and branching, JSONL logging, the config loader |
| `testbed/agents/scripted.py` | **core-engine** | Scripted agents: `honest` (always the cover default; bids its own cost plus a fixed margin), `random`, and `kbit_colluder` (a known k-bit code on a chosen medium, used for calibration) |
| `testbed/agents/` (everything else) | **llm-agents** | The LLM agent, provider adapters, prompt rendering from `Observation`, response parsing, budget guard, price table, cost ledger |
| `testbed/solver/` | **solver-metrics** | Benchmarks π_comp, π_0, π*(k), π_full for N = 2 and 3, K contracts |
| `testbed/metrics/` | **solver-metrics** | MI estimators, encode/decode, Î, φ, Δ_price, Δ_info, ρ, detector D, the counterfactual-replay driver |
| `testbed/studies/study1.py` | **core-engine** | Study 1's 37 cards (plan §4, Study 1) |
| `testbed/studies/study{2,3,4}.py` | later study sessions | Card definitions and study-specific hooks, built on the engine's intervention hooks |
| `testbed/modal_app.py` | **llm-agents** | The Modal runner: fans card × seed runs out to containers, writes logs to a Modal Volume, reads keys from Modal Secrets |
| `tests/` | each component writes `tests/test_<component>_*.py` | |

## Interfaces

- **Agent.** Any object with `act(obs: Observation) -> Action`, `snapshot() -> dict` and `restore(state: dict) -> None`. The engine never formats prompts. It fills `Observation.framing` with plain facts (for example `{"permission": "named:time,private_message", "announced_watched": "msg"}`), and the LLM agent turns those facts into text.
- **Phases per round:** optional `chat` → `prebid` (all firms simultaneously; four media) → `bid` (simultaneous; K contracts) → reveal → optional `probe` (on the probe schedule).
- **Randomness:** costs and z for (seed, round, firm) come from `numpy.random.default_rng([seed, round, firm])`. They are identical across cards (common random numbers) and never depend on agent behaviour.
- **Log** (`runs/<card_id>/<seed>.jsonl`): one header line `{"type": "header", "config": ..., "git_sha": ..., "started": ...}`, then one line per firm per round:
  `{"type": "round", "round", "firm", "z", "costs", "defaults", "prebid", "shown": {rival: {medium: value|"unavailable"}}, "messages_sent", "bids", "won", "price", "profit", "fine", "flags", "probe", "usage"}`
  Metrics read only these files.
- **Checkpoint:** `engine.run(config, until_round=r)` saves state plus agent snapshots. `engine.branch(checkpoint, new_config)` resumes at r + 1. This is how interventions at round 41 are applied.
- **Solver:** `benchmarks(n_firms, k_contracts, cost_low, cost_high, reserve) -> {"pi_comp", "pi_0", "pi_star": {bits: value}, "pi_full"}`, per firm per round. `bits` means bits per firm per round.
- **Metrics:** pure functions over loaded round records, for example `encode(records, medium)`, `decode(records, medium)`, `total_leakage(records)`, `phi(...)`, `harm(records, benchmarks)`, `detector_d(records, medium, window, alpha)`.

## Where things run

- **Experiments run on Modal** (hackathon sponsor credits), never on the development Mac.
  - One container per card × seed, CPU only. The run loop mostly waits on API latency, so many small containers in parallel are cheap.
  - Logs are written to a Modal Volume (`collusion-runs`), mirroring `runs/<card_id>/<seed>.jsonl`, and synced down only for analysis.
  - API keys come from a Modal Secret (`collusion-api-keys`) holding the same variable names as `.env`. Keys never leave Modal or `.env`.
- **The spend ledger is shared across containers.** Budget caps are enforced against a single ledger in Modal storage (for example a `modal.Dict`), with atomic reserve-then-settle: reserve the estimated cost before a call, then settle the actual cost after it. Parallel containers can therefore never jointly exceed `BUDGET_USD_*`. Local runs use the same interface backed by `runs/ledger.jsonl`.
- **Modal compute spend** is tracked separately from API spend and reported in the same `spend` command.
- **The Mac** is used only for editing code, offline tests with scripted agents, and analysis of downloaded logs. It is low on disk, so keep local artifacts small.

## Rules every session follows

- **No paid API calls unless the budget guard allows them.** `BUDGET_USD_*` in `.env` defaults to 0. Tests use scripted agents or recorded fixtures. Paid smoke tests are marked `@pytest.mark.paid` and skipped by default.
- **Never read, print or log key values.** Load them from `.env` with python-dotenv.
- **Sampling parameters are not set for any provider** (Claude rejects `temperature`/`top_p`/`top_k` from 2026-10-21). Record the reasoning/effort setting per agent instead.
- Python 3.11, standard `venv` + `pip install -e ".[llm,dev]"`. `pytest` must pass before merging.
- Commit messages end with the attribution line from the session's instructions.
