import subprocess
import sys
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    ActorState,
    EgoState,
    FrameRecord,
    MetaInfo,
    PlanningState,
    ScenarioRecord,
    SourceInfo,
    TrajectoryPoint,
    TrajectorySource,
)
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


def test_planning_evidence_uses_first_collision_not_deepest_overlap():
    actor = ActorState(
        actor_id="lead",
        type="vehicle",
        x=10.0,
        y=0.0,
        length=4.0,
        width=2.0,
    )
    frames = []
    for timestamp, planned_x in [(1.0, 5.6), (2.0, 10.0)]:
        frames.append(
            FrameRecord(
                timestamp=timestamp,
                ego=EgoState(x=0.0, y=0.0, length=4.0, width=2.0),
                actors_gt=[actor],
                actors_gt_source=ActorGtSource.SIMULATION,
                planning=PlanningState(
                    available=True,
                    trajectory_source=TrajectorySource.PERTURBED_PLANNER,
                    trajectory=[TrajectoryPoint(dt=1.0, x=planned_x, y=0.0)],
                ),
            )
        )
    scenario = ScenarioRecord(
        scenario_id="planning_timing_000001",
        source=SourceInfo(dataset="test", version="v0"),
        meta=MetaInfo(frequency_hz=1.0, duration=2.0),
        frames=frames,
    )

    result = evaluate_planning(scenario)

    assert result.collision_start_time == 1.0
    assert result.min_margin_time == 2.0
    assert result.evidence[0].time == 1.0
