import csv
import json

import pytest

from zhijia_guardian.experiments.compare_runs import compare_runs


def _write_run(root, run_id, method, scenario_ids, macro_f1):
    run = root / run_id
    run.mkdir()
    summary = {
        "num_scenarios": len(scenario_ids),
        "fault_accuracy": macro_f1,
        "fault_macro_f1": macro_f1,
        "root_top1_accuracy": macro_f1,
        "fault_start_time_mae": 0.2,
        "evidence_coverage": 1.0,
        "evidence_correctness": 0.9,
        "hallucination_rate": 0.1,
    }
    meta = {
        "run_id": run_id,
        "method": method,
        "dataset": "manual_json_v0_1",
        "seed": 42,
        "git_commit": "abc123",
    }
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with (run / "eval.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["scenario_id"])
        writer.writeheader()
        for scenario_id in scenario_ids:
            writer.writerow({"scenario_id": scenario_id})
    return run


def test_compare_runs_validates_scenarios_and_ranks_macro_f1(tmp_path):
    run_a = _write_run(tmp_path, "run_a", "rule_only", ["s1", "s2"], 0.6)
    run_b = _write_run(tmp_path, "run_b", "multi_agent_tools", ["s1", "s2"], 0.8)
    output = compare_runs([run_a, run_b], tmp_path / "comparison")
    payload = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    assert payload["scenario_sets_match"] is True
    assert payload["runs"][0]["method"] == "multi_agent_tools"
    assert (output / "comparison.csv").exists()
    assert "Run Comparison" in (output / "comparison.md").read_text(encoding="utf-8")


def test_compare_runs_rejects_different_scenario_sets(tmp_path):
    run_a = _write_run(tmp_path, "run_a", "rule_only", ["s1", "s2"], 0.6)
    run_b = _write_run(tmp_path, "run_b", "multi_agent_tools", ["s1", "s3"], 0.8)
    with pytest.raises(ValueError, match="Scenario set mismatch"):
        compare_runs([run_a, run_b], tmp_path / "comparison")
