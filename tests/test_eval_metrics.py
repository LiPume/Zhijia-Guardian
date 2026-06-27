import pytest

from zhijia_guardian.experiments.eval_metrics import evaluate_one, summarize
from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.scenario import (
    EgoState,
    FrameRecord,
    MetaInfo,
    OracleRecord,
    ScenarioRecord,
    SourceInfo,
)


def _record(scenario_id: str, fault_type: str, fault_time: float | None) -> ScenarioRecord:
    root = "planning" if fault_type == "planning_collision_risk" else "none"
    return ScenarioRecord(
        scenario_id=scenario_id,
        source=SourceInfo(dataset="test", version="v1"),
        meta=MetaInfo(frequency_hz=10, duration=0),
        frames=[FrameRecord(timestamp=0, ego=EgoState(x=0, y=0))],
        oracle=OracleRecord(fault_type=fault_type, root_module=root, fault_start_time=fault_time),
    )


def _diagnosis(
    scenario_id: str,
    fault_type: str,
    root_module: str,
    fault_time: float | None,
) -> DiagnosisRecord:
    return DiagnosisRecord(
        scenario_id=scenario_id,
        predicted_fault_type=fault_type,
        predicted_root_module=root_module,
        predicted_fault_start_time=fault_time,
    )


def test_time_metrics_report_coverage_and_condition_on_correct_fault():
    rows = [
        evaluate_one(
            _record("test_001", "planning_collision_risk", 2.5),
            _diagnosis("test_001", "planning_collision_risk", "planning", 3.0),
        ),
        evaluate_one(
            _record("test_002", "planning_collision_risk", 2.5),
            _diagnosis("test_002", "control_delay", "control", 2.6),
        ),
        evaluate_one(
            _record("test_003", "planning_collision_risk", 2.5),
            _diagnosis("test_003", "planning_collision_risk", "planning", None),
        ),
        evaluate_one(
            _record("test_004", "normal", None),
            _diagnosis("test_004", "normal", "none", None),
        ),
    ]
    summary = summarize(rows)
    assert summary["fault_start_time_coverage"] == 2 / 3
    assert summary["fault_start_time_mae"] == pytest.approx(0.3)
    assert summary["fault_start_time_mae_at_correct_fault"] == pytest.approx(0.5)
    assert summary["fault_start_time_coverage_at_correct_fault"] == 0.5
