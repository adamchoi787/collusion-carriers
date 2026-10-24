# Follow the Bits

**Collusion carriers and countermeasures, measured in bits.** Our entry to the AI Collusion Research Sprint (Apart Research, Poseidon Research and AE Studio, Oct 2026), Track 3: Collusion Carriers and Countermeasures.

We treat collusion between AI agents as information flow, in bits per round, and test countermeasures by where that flow goes:
- **Bits to profit.** A rate–profit frontier says how much profit a coalition can extract from each bit of coordination capacity.
- **Told vs. actual.** Agents are *told* one thing about a channel, a monitor, an identity or a role, while the harness does another. The two sets are kept disjoint, so any collusion that gets through travels where nobody pointed the agents.
- **The testbed.** A procurement auction with private costs and four pluggable pre-bid media (status message, utilisation value, check-in timing, tool-call order). It comes with exact benchmarks, information-flow estimators with exact-zero nulls, and a monitor whose false-alarm rate is controlled.

The full design is in [`plan/research-plan.md`](plan/research-plan.md). The report is linked here once submitted.

> **Status:** testbed, solver, metrics and all four studies' cards are built and tested. LLM runs are in progress; results and logs will be added here.

## Repository layout

| Path | What |
|---|---|
| [`plan/research-plan.md`](plan/research-plan.md) | The research agenda: thesis, four studies, rigour, budgeted execution (§9.1) |
| [`testbed/engine/`](testbed/engine) | Game loop, media and cover defaults, visibility and decoys, messages, belief probes, checkpoints and branching, plugins, JSONL logging |
| [`testbed/agents/`](testbed/agents) | Scripted agents, the LLM agent (prompt rendering, parsing), provider adapters, the spend guard and price table |
| [`testbed/studies/`](testbed/studies) | The 102 test cards: Study 1 (medium isolation, 37), Study 2 (monitoring, 25), Study 3 (identity, 19), Study 4 (roles and the sting, 21) |
| [`testbed/solver/`](testbed/solver/README.md) | Exact benchmarks: competitive, 0-bit, k-bit and full-information profit, for N = 2 and 3 firms |
| [`testbed/metrics/`](testbed/metrics/README.md) | Encode/decode flow, total leakage, harm, detector D, counterfactual replay; estimator calibration in `calibration/` |
| [`testbed/modal_app.py`](testbed/modal_app.py) | Runs card × seed jobs on Modal, with logs on a Volume and a shared spend ledger |
| [`testbed/CONTRACT.md`](testbed/CONTRACT.md) | Interfaces between the components and the log schema |
| [`analysis/`](analysis) | `frontier.py` (the plan's frontier tables), `pilot.py` (pilot jobs, cost summary and gate readings) |
| [`tests/`](tests) | Offline test suite (scripted agents and fake providers; no paid calls) |
| [`reference/track3-brief.md`](reference/track3-brief.md) | The sprint's Track 3 brief, judging rubric and submission rules |

## Quick start (offline, no API keys)

Python 3.11.

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[llm,dev]"
```

```bash
.venv/bin/python -m pytest -q
```

```bash
.venv/bin/python -m testbed.run --list
```

```bash
.venv/bin/python -m testbed.run --card s1-calib-val --seed 0 --agents scripted:kbit_colluder:medium=val,k=2
```

```bash
.venv/bin/python analysis/frontier.py
```

The test suite runs without keys; tests that make paid API calls are marked `paid` and skipped unless `RUN_PAID=1`. A run writes `runs/<card_id>/<seed>.jsonl`, one header line and one line per firm per round (schema in [`testbed/CONTRACT.md`](testbed/CONTRACT.md)). Metrics read only these files.

## Running LLM agents

1. Copy `.env.example` to `.env` and fill in the keys you have. Every provider has a spend cap, `BUDGET_USD_<PROVIDER>`, and a cap of 0 or unset blocks that provider. The guard reserves the estimated cost before each call and settles the actual cost after it.
2. Locally: pass agents as `llm:<provider>/<model>` specs (e.g. `--agents llm:anthropic/claude-haiku-5-5`), or put them in a card's YAML (`--dump-yaml` prints one).
3. On Modal (what we used): one container per card × seed, keys from a Modal Secret, logs on a Volume. See the docstring of [`testbed/modal_app.py`](testbed/modal_app.py) for the one-time setup, then:

```bash
.venv/bin/modal run testbed/modal_app.py::main --jobs jobs.json --concurrency 8
```

```bash
.venv/bin/modal run testbed/modal_app.py::sync --prefix runs
```

```bash
.venv/bin/python -m testbed.agents.spend --backend modal
```

No sampling parameters are sent to any hosted provider. Each agent's reasoning setting is recorded in its log.

## Reproducing the results

*To be completed with the main runs:* the job files, the pre-registration tag, the log archive, and one script that regenerates every number and figure in the report from the raw logs.

## Disclosures

- **Preexisting code:** none. Everything in this repository was written during the sprint (from 23 Oct 2026). The starter repo [poseidon-research/collusion_hackathon](https://github.com/poseidon-research/collusion_hackathon) is cited in the plan, but no code from it is included.
- **LLM usage:** the code, tests and planning documents were written with Claude Code (Claude Opus 5.5) under the authors' direction and review. Every number reported comes from code in this repository run on logged games.
- **Deception and dual use:** the studies deliberately mislead agents (decoy channels, scarecrow monitors, false identity and role claims). All of it is sandboxed and disclosed. See the ethics and dual-use notes in the plan (§6) and the report's appendix.

## License

[MIT](LICENSE).
