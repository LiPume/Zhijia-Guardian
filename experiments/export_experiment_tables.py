#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path


RUN_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/outputs/runs")
DATA_ROOT = Path("/data5/lzx_data/Zhijia-Guardian")
SEEDS = (7, 42, 2026, 3407, 9012)
METHODS = (
    ("rule", "Rule-only"),
    ("no_temporal", "Multi-Agent w/o temporal causal ranking"),
    ("full", "Multi-Agent + Tools"),
)
FINAL_RUNS = (
    ("Manual v0.3", "seed42", "Rule-only", "manual_v0_3_seed42_rule"),
    ("Manual v0.3", "seed42", "Multi-Agent w/o temporal causal ranking", "manual_v0_3_seed42_no_temporal"),
    ("Manual v0.3", "seed42", "Multi-Agent + Tools", "manual_v0_3_seed42_full"),
    ("Manual v0.3", "seed42", "Single-LLM DeepSeek V4 Pro", "manual_v0_3_single_llm_deepseek_v4_pro_seed42"),
    ("CARLA v0.2-riskfix", "held-out test", "Rule-only", "final_carla_fault_riskfix_test_rule_seed42"),
    ("CARLA v0.2-riskfix", "held-out test", "Multi-Agent w/o temporal causal ranking", "final_carla_fault_riskfix_test_no_temporal_seed42"),
    ("CARLA v0.2-riskfix", "held-out test", "Multi-Agent + Tools", "final_carla_fault_riskfix_test_full_seed42"),
    ("CARLA closed-loop v0.1", "all 5 parents", "Rule-only", "final_carla_closed_rule_seed42"),
    ("CARLA closed-loop v0.1", "all 5 parents", "Multi-Agent w/o temporal causal ranking", "final_carla_closed_no_temporal_seed42"),
    ("CARLA closed-loop v0.1", "all 5 parents", "Multi-Agent + Tools", "final_carla_closed_full_seed42"),
    ("CARLA extreme weather v0.1", "night-storm held-out", "Rule-only", "final_carla_weather_test_rule_seed42"),
    ("CARLA extreme weather v0.1", "night-storm held-out", "Multi-Agent w/o temporal causal ranking", "final_carla_weather_test_no_temporal_seed42"),
    ("CARLA extreme weather v0.1", "night-storm held-out", "Multi-Agent + Tools", "final_carla_weather_test_full_seed42"),
    ("nuPlan perturbation v0.1", "5 paired parents", "Rule-only", "final_nuplan_rule_seed42"),
    ("nuPlan perturbation v0.1", "5 paired parents", "Multi-Agent w/o temporal causal ranking", "final_nuplan_no_temporal_seed42"),
    ("nuPlan perturbation v0.1", "5 paired parents", "Multi-Agent + Tools", "final_nuplan_full_seed42"),
)
METRIC_FIELDS = (
    "fault_accuracy",
    "fault_macro_f1",
    "root_top1_accuracy",
    "fault_start_time_coverage",
    "fault_start_time_mae_at_correct_fault",
    "evidence_coverage",
    "evidence_correctness",
    "hallucination_rate",
)


def main() -> None:
    output = Path("docs/tables")
    output.mkdir(parents=True, exist_ok=True)
    _write_main_results(output / "main_results.csv")
    _write_multiseed(output / "manual_multiseed.csv", output / "manual_multiseed_aggregate.csv")
    _write_real_data(output / "real_data_results.csv")
    _write_latency(output / "diagnosis_latency.csv")
    print(f"Exported experiment tables to {output}")


def _write_main_results(path: Path) -> None:
    rows = []
    for dataset, split, display_method, run_id in FINAL_RUNS:
        summary, meta = _load_run(run_id)
        rows.append(
            {
                "dataset": dataset,
                "split": split,
                "method": display_method,
                "run_id": run_id,
                "num_scenarios": summary["num_scenarios"],
                **{field: summary.get(field) for field in METRIC_FIELDS},
                "seed": meta.get("seed"),
                "git_commit": meta.get("git_commit"),
            }
        )
    _write_csv(path, rows)


def _write_multiseed(detail_path: Path, aggregate_path: Path) -> None:
    detail = []
    for seed in SEEDS:
        for suffix, display_method in METHODS:
            run_id = f"manual_v0_3_seed{seed}_{suffix}"
            summary, meta = _load_run(run_id)
            detail.append(
                {
                    "seed": seed,
                    "method": display_method,
                    "run_id": run_id,
                    "num_scenarios": summary["num_scenarios"],
                    **{field: summary.get(field) for field in METRIC_FIELDS},
                    "git_commit": meta.get("git_commit"),
                }
            )
    _write_csv(detail_path, detail)
    aggregate = []
    for _, display_method in METHODS:
        method_rows = [row for row in detail if row["method"] == display_method]
        row = {"method": display_method, "num_seeds": len(SEEDS), "scenarios_per_seed": 72}
        for field in METRIC_FIELDS:
            values = [item[field] for item in method_rows]
            row[f"{field}_mean"] = statistics.mean(values)
            row[f"{field}_std"] = statistics.stdev(values)
            row[f"{field}_min"] = min(values)
            row[f"{field}_max"] = max(values)
        aggregate.append(row)
    _write_csv(aggregate_path, aggregate)


def _write_real_data(path: Path) -> None:
    manifest = json.loads(
        (DATA_ROOT / "datasets/nuscenes_mini/yolo_v0_1/manifest.json").read_text()
    )
    metrics = manifest["aggregate_metrics"]
    rows = [
        {
            "dataset": manifest["dataset"],
            "num_scenarios": manifest["num_scenarios"],
            "num_frames": manifest["num_frames"],
            "detector": manifest["detector"],
            "annotation_recall": metrics["annotation_recall"],
            "key_actor_recall": metrics["key_actor_recall"],
            "detection_precision": metrics["detection_precision"],
            "matched_class_accuracy": metrics["matched_class_accuracy"],
            "fault_oracle_available": manifest["oracle_available"],
            "diagnosis_hypothesis": "perception_miss (5/5 clips; not accuracy)",
        }
    ]
    _write_csv(path, rows)


def _write_latency(path: Path) -> None:
    payload = json.loads(
        (DATA_ROOT / "outputs/benchmarks/diagnosis_latency_manual_v0_3.json").read_text()
    )
    rows = [
        {
            **row,
            "dataset": payload["dataset"],
            "timing_scope": payload["timing_scope"],
            "git_commit": payload["git_commit"],
        }
        for row in payload["rows"]
    ]
    _write_csv(path, rows)


def _load_run(run_id: str) -> tuple[dict, dict]:
    run_dir = RUN_ROOT / run_id
    summary = json.loads((run_dir / "summary.json").read_text())
    meta = json.loads((run_dir / "run_meta.json").read_text())
    return summary, meta


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
