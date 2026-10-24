"""Metrics over JSONL run logs (plan §3.3): information flow, harm, detector D, replay.

Every function takes loaded records (``load_cell``/``load_run``) or a Panel
built from them (``build_panel``; pass a Panel to avoid rebuilding it on every
call). See README.md in this directory for definitions and estimator choices.
"""
from .detector import DetectorResult, detector_d, detector_rates, test_window
from .displacement import cluster_bootstrap, displacement, displacement_ratio
from .flow import Flow, PairFlow, decode, encode, flows_by_medium, phi, total_leakage
from .harm import Harm, harm, harm_from_profit, run_profit, welfare
from .io import load_cell, load_run, load_runs, write_jsonl
from .mi import cmi, p_value, stratified_permutations
from .panel import Panel, build_panel, coarsen_bids, coarsen_costs
from .probes import ProbeAnswer, belief_rate, parse_probe, probe_table
from .replay import ReplayResult, observation_from_log, replay, replay_many

__all__ = [
    "load_cell", "load_run", "load_runs", "write_jsonl", "Panel", "build_panel", "coarsen_costs",
    "coarsen_bids", "cmi", "p_value", "stratified_permutations", "Flow", "PairFlow", "encode",
    "decode", "total_leakage", "phi", "flows_by_medium", "Harm", "harm", "harm_from_profit",
    "run_profit", "welfare", "displacement_ratio", "displacement", "cluster_bootstrap",
    "DetectorResult", "detector_d", "detector_rates", "test_window", "ProbeAnswer", "parse_probe",
    "probe_table", "belief_rate", "ReplayResult", "replay", "replay_many", "observation_from_log",
]
