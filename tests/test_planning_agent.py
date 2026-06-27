import subprocess
import sys
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.tools.planning_eval import evaluate_planning


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_adjacent_lane_plan_does_not_override_control_or_normal_root(tmp_path):
    dataset = tmp_path / "manual_json"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_manual_scenarios.py"),
            "--output",
            str(dataset),
            "--count",
            "72",
            "--seed",
            "42",
            "--clean",
        ],
        cwd=REPO_ROOT,
    )
    adapter = ManualAdapter(dataset)
    expected = {
        "manual_v0_1_000038": "control_delay",
        "manual_v0_1_000044": "normal",
    }
    for scenario_id, fault_type in expected.items():
        record = adapter.load_scenario(scenario_id)
        assert record.oracle and record.oracle.fault_type == fault_type
        assert evaluate_planning(record).trajectory_collision_count == 0
        _, diagnosis = run_diagnosis_graph(record)
        assert diagnosis.predicted_fault_type == fault_type
