import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from zhijia_guardian.baselines.rule_only import diagnose_rule_only
from zhijia_guardian.benchmarks.manual_v0_3 import build_manual_v0_3_records
from zhijia_guardian.graph.diagnosis_graph import run_diagnosis_graph
from zhijia_guardian.tools.run_metrics import run_all_metrics


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manual_generator_count_metadata_and_no_filename_leak(tmp_path):
    output = tmp_path / "manual_json" / "v0_1"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_manual_scenarios.py"),
            "--seed",
            "7",
            "--count",
            "12",
            "--output",
            str(output),
            "--clean",
        ],
        cwd=REPO_ROOT,
    )
    files = sorted(output.rglob("*.json"))
    assert len(files) == 12
    forbidden = [
        "perception_miss",
        "perception_false_positive",
        "perception_confidence_drop",
        "planning_collision_risk",
        "control_delay",
    ]
    for path in files:
        assert not any(label in path.name for label in forbidden)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["source"]["generation"]["generation_seed"] == 7
        assert data["oracle"]["visible_to_diagnosis"] is False
        assert "fault_type" not in data["scenario_id"]


def test_manual_v0_3_balances_labels_and_preserves_observed_boundary():
    records = build_manual_v0_3_records(count=72, seed=42)

    assert len(records) == 72
    assert Counter(record.oracle.fault_type for record in records) == {
        "normal": 12,
        "perception_miss": 12,
        "perception_false_positive": 12,
        "perception_confidence_drop": 12,
        "planning_collision_risk": 12,
        "control_delay": 12,
    }
    for record in records:
        assert record.source.version == "v0_3"
        assert record.scenario_id.startswith("manual_v0_3_")
        assert "oracle" not in record.observed_view()
        assert "generation" not in record.observed_view()["source"]


def test_manual_v0_3_root_evidence_precedes_downstream_control_fault():
    metric_by_fault = {
        "perception_miss": "missed_key_actors",
        "perception_false_positive": "false_positives",
        "perception_confidence_drop": "confidence_drop_events",
        "planning_collision_risk": "trajectory_collision_count",
        "control_delay": "brake_delay",
    }

    for record in build_manual_v0_3_records(count=72, seed=42):
        metrics = run_all_metrics(record)
        fault_type = record.oracle.fault_type
        if fault_type == "normal":
            continue
        root_evidence = next(
            item
            for item in metrics.evidence
            if item.metric_name == metric_by_fault[fault_type] and item.status == "violation"
        )
        assert root_evidence.time == record.oracle.fault_start_time

        control_evidence = next(
            (
                item
                for item in metrics.evidence
                if item.metric_name == "brake_delay" and item.status == "violation"
            ),
            None,
        )
        if control_evidence is not None and record.oracle.root_module in {"perception", "planning"}:
            assert root_evidence.time + 0.25 < control_evidence.time


def test_manual_v0_3_multi_agent_uses_temporal_causality_on_composites():
    records = build_manual_v0_3_records(count=72, seed=42)
    rule_correct = 0
    multi_correct = 0
    composite_count = 0

    for record in records:
        metrics = run_all_metrics(record)
        rule = diagnose_rule_only(record, metrics)
        _, multi = run_diagnosis_graph(record, metrics)
        expected = record.oracle.fault_type
        rule_correct += rule.predicted_fault_type == expected
        multi_correct += multi.predicted_fault_type == expected
        if record.source.generation["difficulty"] == "composite":
            composite_count += 1

    assert composite_count >= 8
    assert multi_correct == len(records)
    assert multi_correct > rule_correct
