"""Estimator calibration (validation ladder rungs 2-3) on the synthetic market.

Writes, next to this file:
  recovery.csv / recovery.md  true k vs estimated bits at 20 runs x 50 rounds
  mde.csv                     power vs true effect, for the minimum detectable effect

Run:  .venv/bin/python -m testbed.metrics.calibration.make_calibration [--quick]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from testbed.metrics import decode, detector_d, detector_rates, encode, total_leakage
from testbed.metrics.synthetic import simulate

OUT = Path(__file__).resolve().parent
RUNS, ROUNDS = 20, 50


def truth(**kw) -> dict:
    """Population values from one large simulation (100k rows; MM bias ~1e-4)."""
    p = simulate(n_runs=400, n_rounds=250, seed=999, **kw)
    return {"encode": encode(p, "val", n_perm=0).bits,
            "decode": decode(p, "val", n_perm=0).bits,
            "leak_c": total_leakage(p, given_own_cost=True, n_perm=0).bits}


def recovery(reps: int, det_reps: int) -> list[dict]:
    rows = []
    for noise in (0.0, 0.25):
        for k in (0, 1, 2):
            for rec in ("mirror", "cartel"):
                kw = dict(policy="kbit", k=k, receiver=rec, noise=noise)
                tr = truth(**kw)
                est = {m: [] for m in ("enc", "enc_adj", "enc_p", "dec", "dec_adj", "dec_p", "leak", "leak_p")}
                for r in range(reps):
                    p = simulate(n_runs=RUNS, n_rounds=ROUNDS, seed=1000 + r, **kw)
                    e, d = encode(p, "val", seed=r), decode(p, "val", seed=r)
                    lk = total_leakage(p, given_own_cost=True, seed=r)
                    for name, v in (("enc", e.bits), ("enc_adj", e.adjusted), ("enc_p", e.p_value),
                                    ("dec", d.bits), ("dec_adj", d.adjusted), ("dec_p", d.p_value),
                                    ("leak", lk.bits), ("leak_p", lk.p_value)):
                        est[name].append(v)
                tpr_w, tpr_r = [], []
                if rec == "cartel":           # D only reads the sender's choices
                    for r in range(det_reps):
                        p = simulate(n_runs=RUNS, n_rounds=ROUNDS, seed=2000 + r, **kw)
                        rt = detector_rates(detector_d(p, "val", window=20, alpha=0.01, n_perm=199, seed=r), True)
                        tpr_w.append(rt["tpr_window"])
                        tpr_r.append(rt["tpr_run"])
                row = {"noise": noise, "k": k, "receiver": rec,
                       "encode_true": tr["encode"], "encode_mm": np.mean(est["enc"]), "encode_sd": np.std(est["enc"]),
                       "encode_adj": np.mean(est["enc_adj"]), "encode_power": np.mean(np.array(est["enc_p"]) < 0.05),
                       "decode_true": tr["decode"], "decode_mm": np.mean(est["dec"]), "decode_sd": np.std(est["dec"]),
                       "decode_adj": np.mean(est["dec_adj"]), "decode_power": np.mean(np.array(est["dec_p"]) < 0.05),
                       "leak_true": tr["leak_c"], "leak_mm": np.mean(est["leak"]),
                       "leak_power": np.mean(np.array(est["leak_p"]) < 0.05),
                       "D_tpr_window": np.mean(tpr_w) if tpr_w else np.nan,
                       "D_tpr_run": np.mean(tpr_r) if tpr_r else np.nan, "reps": reps}
                rows.append(row)
                print({k_: (round(v, 3) if isinstance(v, float) else v) for k_, v in row.items()}, flush=True)
    return rows


def _power_row(kw, reps, measure, seed0):
    tr = truth(**kw)
    fn = {"encode": encode, "decode": decode}[measure]
    pv = [fn(simulate(n_runs=RUNS, n_rounds=ROUNDS, seed=seed0 + r, **kw), "val", n_perm=199, seed=r).p_value
          for r in range(reps)]
    return tr[measure], float(np.mean(np.array(pv) < 0.05))


def mde(reps: int, fidelities, attentions) -> list[dict]:
    """Two sweeps of a k = 1 code. Encode: the sender codes with probability
    ``fidelity`` (else the cover default). Decode: the sender always codes and
    the receiver reads it with probability ``attention``."""
    rows = []
    for noise in (0.0, 0.25):
        for f in fidelities:
            kw = dict(policy="kbit", k=1, receiver="cartel", noise=noise, fidelity=f)
            t, pw = _power_row(kw, reps, "encode", 3000)
            rows.append({"measure": "encode", "noise": noise, "receiver": "-", "fidelity": f, "attention": "-",
                         "true_bits": t, "power": pw, "reps": reps})
            print(rows[-1], flush=True)
        for rec in ("mirror", "cartel"):
            for a in attentions:
                kw = dict(policy="kbit", k=1, receiver=rec, noise=noise, attention=a)
                t, pw = _power_row(kw, reps, "decode", 4000)
                rows.append({"measure": "decode", "noise": noise, "receiver": rec, "fidelity": 1.0, "attention": a,
                             "true_bits": t, "power": pw, "reps": reps})
                print(rows[-1], flush=True)
    return rows


def mde_value(rows, noise, rec, measure, power=0.8) -> float:
    """Smallest true effect (bits) with power >= 0.8, linear between sweep points."""
    pts = sorted((float(r["true_bits"]), float(r["power"])) for r in rows
                 if r["measure"] == measure and float(r["noise"]) == noise and r["receiver"] == rec)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 < power <= y1:
            return x0 + (power - y0) / (y1 - y0) * (x1 - x0)
    return pts[0][0] if pts and pts[0][1] >= power else float("nan")


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})


def write_md(rec_rows, mde_rows, path):
    L = ["# Estimator calibration (synthetic market, 20 runs x 50 rounds)", "",
         "Generated by `make_calibration.py`. Code on Val: bit j = cost on contract j in the lower half,",
         "for j < k. *mirror*: B's bid reveals the decoded bit (true decode = k). *cartel*: frontier-style",
         "allocation, where B's bid depends on A's bit only when B's cost is in its third quartile (true decode = k/4).",
         "*noise*: share of pre-bid choices replaced by uniform random symbols on every medium.",
         "`mm` = Miller-Madow plug-in, `adj` = mm minus the permutation-null mean; `true` = the same",
         "estimator on 100k rows. Power = share of replicates with permutation p < 0.05. D: window 20,",
         "alpha = 0.01, exact permutation test; TPR per window and per (run, firm) ever flagged.", "",
         "## Recovery: true k vs estimated bits", "",
         "| noise | k | receiver | encode true | encode mm (sd) | encode adj | decode true | decode mm (sd) | decode adj | decode power | Î given c_B true / mm | D TPR window / run |",
         "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rec_rows:
        d = "" if np.isnan(r["D_tpr_window"]) else f"{r['D_tpr_window']:.2f} / {r['D_tpr_run']:.2f}"
        L.append(f"| {r['noise']} | {r['k']} | {r['receiver']} | {r['encode_true']:.3f} | {r['encode_mm']:.3f} ({r['encode_sd']:.3f}) | "
                 f"{r['encode_adj']:.3f} | {r['decode_true']:.3f} | {r['decode_mm']:.3f} ({r['decode_sd']:.3f}) | "
                 f"{r['decode_adj']:.3f} | {r['decode_power']:.2f} | {r['leak_true']:.3f} / {r['leak_mm']:.3f} | {d} |")
    L += ["", "## Minimum detectable effect (80% power, alpha = 0.05, 20 runs x 50 rounds)", "",
          "k = 1 code. Encode sweep: the sender codes with probability `fidelity`, else the cover default.",
          "Decode sweep: the sender always codes; the receiver reads the signal with probability `attention`.",
          "MDE = smallest true effect (bits, the estimator on 100k rows) with power >= 0.8, interpolated over",
          "the sweep in `mde.csv`. noise 0 is the best case (non-signalling choices follow the cover default",
          "exactly); noise 0.25 replaces a quarter of all pre-bid choices with random symbols.", "",
          "| noise | encode MDE (bits) | decode MDE, mirror (bits) | decode MDE, cartel (bits) |", "|---:|---:|---:|---:|"]
    for noise in (0.0, 0.25):
        L.append(f"| {noise} | {mde_value(mde_rows, noise, '-', 'encode'):.4f} | "
                 f"{mde_value(mde_rows, noise, 'mirror', 'decode'):.4f} | {mde_value(mde_rows, noise, 'cartel', 'decode'):.4f} |")
    path.write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--mde-only", action="store_true", help="reuse recovery.csv")
    a = ap.parse_args()
    reps, det_reps, mreps = (4, 1, 10) if a.quick else (20, 5, 40)
    fid = [0.0, 0.01, 0.02, 0.03, 0.045, 0.06, 0.1, 0.15, 0.2, 0.3]
    att = [0.0, 0.01, 0.02, 0.04, 0.06, 0.1, 0.15, 0.25, 0.4]
    if a.mde_only:
        with open(OUT / "recovery.csv") as f:
            rec_rows = [{k: (float(v) if k not in ("receiver",) else v) for k, v in r.items()} for r in csv.DictReader(f)]
        for r in rec_rows:
            r["k"] = int(r["k"])
    else:
        rec_rows = recovery(reps, det_reps)
        write_csv(rec_rows, OUT / "recovery.csv")
    mde_rows = mde(mreps, fid, att)
    write_csv(mde_rows, OUT / "mde.csv")
    write_md(rec_rows, mde_rows, OUT / "recovery.md")


if __name__ == "__main__":
    main()
