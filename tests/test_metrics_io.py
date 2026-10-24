import json

import numpy as np

from testbed.metrics import build_panel, load_cell, load_run, write_jsonl
from testbed.metrics.panel import MISSING, coarsen_bids, coarsen_costs
from testbed.metrics.synthetic import simulate, to_records


def test_roundtrip_through_jsonl(tmp_path):
    p = simulate(n_runs=3, n_rounds=10, policy="kbit", k=1, seed=4)
    recs = to_records(p, card_id="Calib-Val")
    for ri in range(3):
        write_jsonl([r for r in recs if r["run"] == p.run_ids[ri]], tmp_path / f"{ri}.jsonl")
    loaded = load_cell(tmp_path)
    assert {r["run"] for r in loaded} == {f"Calib-Val/{i}" for i in range(3)}
    q = build_panel(loaded)
    for name in ("costs", "z", "prebid", "shown", "won", "profit", "round", "prev_won", "has_prev"):
        np.testing.assert_array_equal(getattr(q, name), getattr(p, name), err_msg=name)
    np.testing.assert_array_equal(np.isnan(q.bids), np.isnan(p.bids))
    assert (q.cost_low, q.cost_high, q.reserve) == (1, 12, 10.0)


def test_loader_tolerates_schema_variants(tmp_path):
    lines = [{"type": "header", "config": {"card_id": "x", "seed": 7, "cost_low": 1, "cost_high": 12}}]
    for t in (1, 2):
        for f in (0, 1):
            lines.append({"type": "round", "round": t, "firm": f, "z": 1, "costs": [1, 2, 3, 4],
                          "defaults": {"msg": 1}, "prebid": {"msg": 2},
                          "shown": {str(1 - f): {"msg": 3, "val": "unavailable"}},
                          "bids": [10, None, 9.5, None], "won": [0] if f == 0 else [],
                          "price": None, "profit": 9.0, "fine": 0})
    path = tmp_path / "7.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines))
    p = build_panel(load_run(path))
    assert p.run_ids == ["x/7"]
    assert p.won[:, 0, 0].all() and not p.won[:, 1].any()       # won as a list of indices
    assert p.shown[0, 0, 1, 0] == 3 and p.shown[0, 0, 1, 1] == MISSING
    assert np.isnan(p.bids[0, 0, 1]) and p.bids[0, 0, 2] == 9.5
    assert p.has_prev.tolist() == [False, True]


def test_coarsening():
    assert coarsen_costs(np.arange(1, 13), 1, 12, 4).tolist() == [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3]
    b = coarsen_bids(np.array([np.nan, 9.5, 10.0, 10.0, 9.5]))
    assert b[0] == 0 and len(set(b[1:])) == 2 and 0 not in b[1:]
