import pytest

from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    EgoState,
    FrameRecord,
    MetaInfo,
    OracleRecord,
    ScenarioRecord,
    SourceInfo,
)


def minimal_record(**kwargs):
    data = {
        "scenario_id": "manual_v0_1_000001",
        "source": SourceInfo(dataset="manual_json", version="v0_1", raw_tokens={}),
        "meta": MetaInfo(frequency_hz=10, duration=0),
        "frames": [
            FrameRecord(
                timestamp=0,
                ego=EgoState(x=0, y=0),
                actors_gt=[],
                actors_gt_source=ActorGtSource.UNAVAILABLE,
            )
        ],
        "events_observed": [],
        "oracle": OracleRecord(
            fault_type="control_delay",
            root_module="control",
            fault_start_time=4.2,
        ),
    }
    data.update(kwargs)
    return ScenarioRecord(**data)


def test_observed_view_excludes_oracle():
    record = minimal_record()
    observed = record.observed_view()
    assert "oracle" not in observed
    assert record.load_oracle_for_eval().fault_type == "control_delay"


def test_scenario_id_rejects_label_leakage():
    with pytest.raises(ValueError):
        minimal_record(scenario_id="perception_miss_001")


def test_oracle_visible_to_diagnosis_must_be_false():
    with pytest.raises(ValueError):
        OracleRecord(visible_to_diagnosis=True)
