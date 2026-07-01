#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.baselines import diagnose_rule_only
from zhijia_guardian.graph import (
    run_diagnosis_graph,
    run_diagnosis_graph_no_temporal_causal,
)
from zhijia_guardian.tools.run_metrics import run_all_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark deterministic diagnosis latency.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.repeats <= 0:
        raise ValueError("repeats must be positive")
    adapter = ManualAdapter(args.dataset)
    records = [adapter.load_scenario(item) for item in adapter.list_scenarios()]
    methods = {
        "rule_only": _rule_only,
        "multi_agent_no_temporal_causal": run_diagnosis_graph_no_temporal_causal,
        "multi_agent_tools": run_diagnosis_graph,
    }
    for function in methods.values():
        function(records[0])

    rows = []
    for method, function in methods.items():
        latencies_ms = []
        started = time.perf_counter()
        for _ in range(args.repeats):
            for record in records:
                sample_started = time.perf_counter()
                function(record)
                latencies_ms.append((time.perf_counter() - sample_started) * 1000.0)
        elapsed = time.perf_counter() - started
        rows.append(
            {
                "method": method,
                "num_scenarios": len(records),
                "repeats": args.repeats,
                "num_measurements": len(latencies_ms),
                "mean_ms_per_scenario": round(statistics.mean(latencies_ms), 6),
                "median_ms_per_scenario": round(statistics.median(latencies_ms), 6),
                "p95_ms_per_scenario": round(_percentile(latencies_ms, 0.95), 6),
                "throughput_scenarios_per_second": round(len(latencies_ms) / elapsed, 3),
            }
        )
    payload = {
        "schema_version": "diagnosis_latency_v1",
        "dataset": str(Path(args.dataset).resolve()),
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "timing_scope": "canonical_scenario_to_diagnosis_including_metric_tools",
        "rows": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


def _rule_only(record):
    metrics = run_all_metrics(record)
    return metrics, diagnose_rule_only(record, metrics)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
