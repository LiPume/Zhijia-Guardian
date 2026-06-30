import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from zhijia_guardian.adapters import CarlaAdapter
from zhijia_guardian.baselines.rule_only import diagnose_rule_only
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.tools.run_metrics import run_all_metrics


DATASET_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/datasets/carla/closed_loop_v0_1")


@pytest.mark.skipif(not DATASET_ROOT.exists(), reason="CARLA closed-loop benchmark not found")
def test_carla_closed_loop_outcomes_and_temporal_root_cause():
    manifest = json.loads((DATASET_ROOT / "raw" / "labels" / "manifest.json").read_text())
    rows = manifest["scenarios"]

    assert manifest["num_scenarios"] == 15
    assert Counter((row["case"], row["outcome"]["collision"]) for row in rows) == {
        ("normal", False): 5,
        ("control_delay", True): 5,
        ("planning_collision_risk", True): 5,
    }
    parents_by_split = defaultdict(set)
    for row in rows:
        parents_by_split[row["split"]].add(row["parent_group"])
        assert row["case"] not in row["scenario_id"]
    assert parents_by_split["train"].isdisjoint(parents_by_split["val"])
    assert parents_by_split["train"].isdisjoint(parents_by_split["test"])
    assert parents_by_split["val"].isdisjoint(parents_by_split["test"])

    observed_adapter = CarlaAdapter(DATASET_ROOT / "raw" / "logs")
    assert all(
        observed_adapter.load_scenario(scenario_id).oracle is None
        for scenario_id in observed_adapter.list_scenarios()
    )

    adapter = CarlaAdapter(DATASET_ROOT / "raw" / "logs", DATASET_ROOT / "raw" / "labels")
    rule_correct = 0
    multi_correct = 0
    for scenario_id in adapter.list_scenarios():
        scenario = adapter.load_scenario(scenario_id)
        metrics = run_all_metrics(scenario)
        rule = diagnose_rule_only(scenario, metrics)
        _, multi = run_diagnosis_graph(scenario, metrics)
        expected = scenario.oracle.fault_type
        rule_correct += rule.predicted_fault_type == expected
        multi_correct += multi.predicted_fault_type == expected
        if expected == "planning_collision_risk":
            planning_time = next(
                item.time for item in metrics.evidence if item.metric_name == "trajectory_collision_count"
            )
            control_time = next(item.time for item in metrics.evidence if item.metric_name == "brake_delay")
            assert planning_time + 0.25 < control_time
            assert rule.predicted_fault_type == "control_delay"
            assert multi.predicted_fault_type == "planning_collision_risk"

    assert rule_correct == 10
    assert multi_correct == 15
