import json
import math

from zhijia_guardian.adapters import SafeBenchAdapter
from zhijia_guardian.graph import run_diagnosis_graph


def test_safebench_planning_export_maps_ego_events_and_missing_modules(tmp_path):
    export_path = tmp_path / "records.json"
    export_path.write_text(
        json.dumps(
            {
                "format": "safebench_records_v0_1",
                "scenario_category": "planning",
                "safebench_commit": "dec2269",
                "carla_version": "0.9.13",
                "fixed_delta_seconds": 0.1,
                "records": [
                    {
                        "data_id": 7,
                        "scenario_id": 1,
                        "route_id": 4,
                        "scenario_folder": "human",
                        "frames": [
                            {
                                "current_game_time": 10.0,
                                "ego_velocity": 5.0,
                                "ego_x": 1.0,
                                "ego_y": 2.0,
                                "ego_yaw": 90.0,
                                "criteria": {"collision": "RUNNING", "off_road": "RUNNING"},
                            },
                            {
                                "current_game_time": 10.1,
                                "ego_velocity": 4.0,
                                "ego_acceleration_x": -1.0,
                                "ego_x": 1.0,
                                "ego_y": 2.4,
                                "ego_yaw": 90.0,
                                "criteria": {"collision": "FAILURE", "off_road": "RUNNING"},
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    adapter = SafeBenchAdapter(export_path)
    assert adapter.list_scenarios() == ["safebench_v0_1_000007"]
    record = adapter.load_scenario("safebench_v0_1_000007")

    assert record.source.dataset == "safebench"
    assert record.oracle is None
    assert math.isclose(record.frames[0].ego.vx, 0.0, abs_tol=1e-8)
    assert math.isclose(record.frames[0].ego.vy, 5.0)
    assert not record.frames[0].perception.available
    assert not record.frames[0].planning.available
    assert not record.frames[0].control.available
    assert [event.event_type for event in record.events_observed] == ["safebench_collision"]
    assert "oracle" not in record.observed_view()

    _, diagnosis = run_diagnosis_graph(record)
    assert diagnosis.predicted_fault_type == "uncertain"
    assert diagnosis.predicted_root_module == "unknown"


def test_safebench_adapter_rejects_duplicate_data_ids(tmp_path):
    record = {
        "data_id": 1,
        "scenario_id": 1,
        "route_id": 4,
        "scenario_folder": "human",
        "frames": [{"current_game_time": 0.0, "ego_x": 0.0, "ego_y": 0.0}],
    }
    export_path = tmp_path / "records.json"
    export_path.write_text(
        json.dumps(
            {
                "format": "safebench_records_v0_1",
                "scenario_category": "planning",
                "safebench_commit": "dec2269",
                "carla_version": "0.9.13",
                "fixed_delta_seconds": 0.1,
                "records": [record, record],
            }
        ),
        encoding="utf-8",
    )

    try:
        SafeBenchAdapter(export_path)
    except ValueError as exc:
        assert "duplicate data_id" in str(exc)
    else:
        raise AssertionError("duplicate SafeBench data_id should fail")
