import json
import subprocess
import sys
from pathlib import Path

import pytest

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.benchmarks.manual_v0_3 import build_manual_v0_3_records
from zhijia_guardian.experiments.run_eval import run_multi_agent_eval
from zhijia_guardian.graph import DiagnosisGraph, run_diagnosis_graph
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.tools.run_metrics import run_all_metrics


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_multi_agent_demo_eval_outputs_trace_and_evidence(tmp_path):
    dataset_dir = tmp_path / "canonical_demo"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_canonical_demo.py"),
            "--output-dir",
            str(dataset_dir),
        ],
        cwd=REPO_ROOT,
    )
    run_dir = run_multi_agent_eval(
        dataset=dataset_dir,
        run_id="pytest_multi_agent_demo",
        output_root=tmp_path / "runs",
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["num_scenarios"] == 6
    assert summary["fault_accuracy"] >= 0.8
    assert summary["evidence_coverage"] == 1.0
    assert summary["hallucination_rate"] == 0.0
    assert (run_dir / "run_report.md").exists()
    assert (run_dir / "artifacts_manifest.json").exists()
    assert (run_dir / "figures" / "confusion_matrix.svg").exists()
    assert (run_dir / "tables" / "errors.csv").exists()
    assert (run_dir / "tables" / "leaderboard.csv").exists()
    assert (run_dir / "failure_samples.jsonl").exists()
    assert (run_dir / "tables" / "failure_samples.csv").exists()

    diagnosis = json.loads((run_dir / "diagnoses" / "manual_v0_1_000001.json").read_text(encoding="utf-8"))
    assert diagnosis["method"] == "multi_agent_tools"
    assert diagnosis["agent_trace"]
    assert diagnosis["candidate_root_causes"]
    assert (run_dir / "figures" / "manual_v0_1_000001_bev.svg").exists()
    assert (run_dir / "figures" / "manual_v0_1_000001_timeline.svg").exists()
    report_text = (run_dir / "reports" / "manual_v0_1_000001.md").read_text(encoding="utf-8")
    assert "../figures/manual_v0_1_000001_bev.svg" in report_text
    assert "../figures/manual_v0_1_000001_timeline.svg" in report_text
    evidence_ids = {item["evidence_id"] for item in diagnosis["evidence"]}
    for claim in diagnosis["claims"]:
        assert claim["evidence_ids"]
        assert set(claim["evidence_ids"]).issubset(evidence_ids)

    failure_sample_path = run_dir / "failure_samples" / "manual_v0_1_000001" / "failure_sample.json"
    assert failure_sample_path.exists()
    failure_sample = json.loads(failure_sample_path.read_text(encoding="utf-8"))
    assert failure_sample["schema_version"] == "failure_sample_v1"
    assert failure_sample["oracle_visibility"] == "evaluation_only"
    assert failure_sample["scenario_id"] == "manual_v0_1_000001"
    assert failure_sample["true_fault_type"] == "perception_miss"
    assert failure_sample["recommended_data"]
    assert failure_sample["regression_test_config"]["diagnosis_input"] == "observed_view_only"
    assert len(failure_sample["scenario_record_hash"]) == 64
    assert not (run_dir / "failure_samples" / "manual_v0_1_000004" / "failure_sample.json").exists()


def test_multi_agent_graph_observed_view_hides_oracle_and_generation(tmp_path):
    dataset_dir = tmp_path / "manual_json"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_manual_scenarios.py"),
            "--output",
            str(dataset_dir),
            "--count",
            "6",
            "--seed",
            "42",
            "--clean",
        ],
        cwd=REPO_ROOT,
    )
    record = ManualAdapter(dataset_dir).load_scenario("manual_v0_1_000001")
    observed = record.observed_view()
    assert "oracle" not in observed
    assert "generation" not in observed["source"]

    _, diagnosis = run_diagnosis_graph(record)
    serialized = diagnosis.model_dump(mode="json")
    assert "oracle" not in json.dumps(serialized)


def test_diagnosis_graph_has_explicit_fan_out_fan_in_and_oracle_free_state():
    record = build_manual_v0_3_records(count=6, seed=7)[0]
    graph = DiagnosisGraph()

    topology = graph.describe()
    assert [node["name"] for node in topology] == [
        "metric_agent",
        "scene_agent",
        "perception_agent",
        "planning_agent",
        "control_agent",
        "root_cause_agent",
    ]
    assert topology[-1]["stage"] == "fan_in"
    assert set(topology[-1]["depends_on"]) == {
        "scene_agent",
        "perception_agent",
        "planning_agent",
        "control_agent",
    }

    state = graph.initialize_state(record)
    assert state.scenario.oracle is None
    assert state.scenario.source.generation == {}
    assert record.oracle is not None
    assert record.source.generation


def test_diagnosis_graph_trace_matches_node_execution_and_module_availability():
    record = next(
        item
        for item in build_manual_v0_3_records(count=24, seed=42)
        if item.source.raw_log_id == "perception_like_nuscenes"
    )
    state = DiagnosisGraph().invoke(record)

    expected = [
        "metric_agent",
        "scene_agent",
        "perception_agent",
        "planning_agent",
        "control_agent",
        "root_cause_agent",
    ]
    assert state.executed_nodes == expected
    assert [step.agent_name for step in state.trace] == expected
    assert state.module_diagnoses["planning"].status == "skipped"
    assert state.module_diagnoses["control"].status == "skipped"
    assert state.diagnosis is not None
    assert state.diagnosis.predicted_root_module == record.oracle.root_module


def test_diagnosis_graph_temporal_fan_in_recovers_composite_upstream_root():
    for record in build_manual_v0_3_records(count=72, seed=42):
        if record.source.generation["difficulty"] != "composite":
            continue
        if record.oracle.root_module not in {"perception", "planning"}:
            continue
        metrics = run_all_metrics(record)
        has_control_violation = any(
            item.metric_name == "brake_delay" and item.status == "violation"
            for item in metrics.evidence
        )
        if not has_control_violation:
            continue

        state = DiagnosisGraph().invoke(record, metrics)
        assert state.diagnosis is not None
        assert state.diagnosis.predicted_fault_type == record.oracle.fault_type
        assert state.diagnosis.predicted_root_module == record.oracle.root_module
        assert state.diagnosis.candidate_root_causes[0].root_module == record.oracle.root_module
        return
    raise AssertionError("seed 42 should contain an upstream + control-delay composite")


def test_diagnosis_graph_rejects_metrics_from_another_scenario():
    record = build_manual_v0_3_records(count=6, seed=42)[0]
    metrics = MetricsRecord(scenario_id="another_scenario")

    with pytest.raises(ValueError, match="does not match"):
        DiagnosisGraph().initialize_state(record, metrics)
