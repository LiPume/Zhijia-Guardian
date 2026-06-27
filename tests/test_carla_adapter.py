import json
from math import pi

import pytest

from zhijia_guardian.adapters import CarlaAdapter
from zhijia_guardian.schemas.scenario import ActorGtSource, TrajectorySource
from zhijia_guardian.tools.run_metrics import run_all_metrics


def _transform(x: float, y: float, yaw: float = 0.0) -> dict:
    return {
        "location": {"x": x, "y": y, "z": 0.2},
        "rotation": {"pitch": 0.0, "yaw": yaw, "roll": 0.0},
    }


def _actor(actor_id: int, x: float, y: float, yaw: float = 0.0) -> dict:
    return {
        "actor_id": actor_id,
        "type_id": "vehicle.tesla.model3",
        "transform": _transform(x, y, yaw),
        "velocity": {"x": 5.0, "y": 0.0, "z": 0.0},
        "acceleration": {"x": -0.5, "y": 0.0, "z": 0.0},
        "bounding_box": {"extent": {"x": 2.4, "y": 1.0, "z": 0.75}},
        "is_key_actor": actor_id == 2,
    }


def _raw_log(scenario_id: str = "carla_v0_1_000001") -> dict:
    ego = _actor(1, 10.0, 20.0, 90.0)
    target = _actor(2, 20.0, 20.0)
    return {
        "log_version": "carla_log_v0_1",
        "scenario_id": scenario_id,
        "carla_version": "0.9.15",
        "map_name": "Town03",
        "fixed_delta_seconds": 0.1,
        "frames": [
            {
                "frame_id": 100,
                "simulation_time": 5.0,
                "ego": ego,
                "actors": [target],
                "perception": {
                    "available": True,
                    "detection_source": "synthetic_from_annotation",
                    "detections": [
                        {
                            "track_id": "det_2",
                            "type": "vehicle",
                            "confidence": 0.95,
                            "transform": _transform(20.1, 20.0),
                            "bounding_box": {"extent": {"x": 2.3, "y": 0.95, "z": 0.75}},
                            "matched_actor_id": 2,
                        }
                    ],
                },
                "planning": {
                    "available": True,
                    "trajectory_source": "offline_planner",
                    "trajectory": [
                        {"dt": 0.0, "transform": _transform(10.0, 20.0, 90.0), "speed": 5.0},
                        {"dt": 1.0, "transform": _transform(10.0, 25.0, 90.0), "speed": 5.0},
                    ],
                    "intent": "lane_follow",
                    "target_speed": 5.0,
                },
                "control": {"available": True, "steer": 0.1, "throttle": 0.2, "brake": 0.0},
                "map": {"available": True, "lane_id": "12:-1", "road_id": 12, "speed_limit": 13.9},
                "events": [
                    {
                        "event_type": "lane_invasion",
                        "description": "Crossed a lane marking",
                        "attributes": {"marking_type": "Broken"},
                    }
                ],
            },
            {
                "frame_id": 101,
                "simulation_time": 5.1,
                "ego": ego,
                "actors": [target],
                "perception": {"available": False, "detections": []},
                "planning": {"available": False, "trajectory": []},
                "control": {"available": True, "steer": 0.0, "throttle": 0.0, "brake": 0.4},
                "map": {"available": False},
                "events": [],
            },
        ],
    }


def test_carla_adapter_converts_units_and_keeps_oracle_out_of_observed_view(tmp_path):
    logs = tmp_path / "logs"
    labels = tmp_path / "labels"
    logs.mkdir()
    labels.mkdir()
    scenario_id = "carla_v0_1_000001"
    (logs / "000001.json").write_text(json.dumps(_raw_log(scenario_id)), encoding="utf-8")
    (labels / f"{scenario_id}.label.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "oracle": {
                    "visible_to_diagnosis": False,
                    "fault_type": "planning_collision_risk",
                    "root_module": "planning",
                    "fault_start_time": 0.1,
                },
            }
        ),
        encoding="utf-8",
    )

    adapter = CarlaAdapter(logs, labels)
    assert adapter.list_scenarios() == [scenario_id]
    record = adapter.load_scenario(scenario_id)

    assert record.meta.frequency_hz == pytest.approx(10.0)
    assert record.meta.duration == pytest.approx(0.1)
    assert record.frames[0].ego.yaw == pytest.approx(pi / 2.0)
    assert record.frames[0].ego.length == pytest.approx(4.8)
    assert record.frames[0].actors_gt_source == ActorGtSource.SIMULATION
    assert record.frames[0].actors_gt[0].width == pytest.approx(2.0)
    assert record.frames[0].planning.trajectory_source == TrajectorySource.OFFLINE_PLANNER
    assert record.events_observed[0].timestamp == pytest.approx(0.0)
    assert record.oracle is not None
    assert "oracle" not in record.observed_view()
    assert "generation" not in record.observed_view()["source"]
    assert run_all_metrics(record).scenario_id == scenario_id


def test_carla_adapter_does_not_load_labels_without_explicit_label_dir(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "000001.json").write_text(json.dumps(_raw_log()), encoding="utf-8")

    record = CarlaAdapter(logs).load_scenario("carla_v0_1_000001")

    assert record.oracle is None


def test_carla_adapter_rejects_mismatched_label(tmp_path):
    logs = tmp_path / "logs"
    labels = tmp_path / "labels"
    logs.mkdir()
    labels.mkdir()
    (logs / "000001.json").write_text(json.dumps(_raw_log()), encoding="utf-8")
    (labels / "carla_v0_1_000001.label.json").write_text(
        json.dumps(
            {
                "scenario_id": "carla_v0_1_999999",
                "oracle": {"visible_to_diagnosis": False, "fault_type": None, "root_module": None},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="scenario_id mismatch"):
        CarlaAdapter(logs, labels).load_scenario("carla_v0_1_000001")
