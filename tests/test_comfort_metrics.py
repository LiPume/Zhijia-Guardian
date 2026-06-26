from zhijia_guardian.schemas.scenario import EgoState, FrameRecord, MetaInfo, ScenarioRecord, SourceInfo
from zhijia_guardian.tools.comfort_eval import evaluate_comfort
from zhijia_guardian.tools.run_metrics import run_all_metrics


def test_comfort_metrics_emit_auxiliary_evidence_and_series():
    record = ScenarioRecord(
        scenario_id="manual_v0_1_900001",
        source=SourceInfo(dataset="manual_json", version="v0_1", raw_log_id="unit_test"),
        meta=MetaInfo(frequency_hz=1.0, duration=2.0),
        frames=[
            FrameRecord(timestamp=0.0, ego=EgoState(x=0.0, y=0.0, yaw=0.0, vx=0.0, vy=0.0)),
            FrameRecord(timestamp=1.0, ego=EgoState(x=5.0, y=0.0, yaw=0.0, vx=5.0, vy=0.0)),
            FrameRecord(timestamp=2.0, ego=EgoState(x=10.0, y=0.0, yaw=1.0, vx=5.0, vy=0.0)),
        ],
    )

    result = evaluate_comfort(
        record,
        acceleration_threshold=4.0,
        jerk_threshold=4.0,
        yaw_rate_threshold=0.5,
    )
    evidence_by_metric = {item.metric_name: item for item in result.evidence}

    assert evidence_by_metric["max_abs_acceleration"].status == "violation"
    assert evidence_by_metric["max_abs_jerk"].status == "violation"
    assert evidence_by_metric["max_abs_yaw_rate"].status == "violation"
    assert all(not item.supports for item in result.evidence)

    series_names = {item.name for item in result.series}
    assert "ego_speed" in series_names
    assert "ego_longitudinal_acceleration" in series_names
    assert "ego_jerk" in series_names
    assert "ego_yaw_rate" in series_names

    metrics = run_all_metrics(record)
    assert any(item.metric_name == "max_abs_yaw_rate" for item in metrics.evidence)
    assert any(item.name == "ego_jerk" for item in metrics.series)
