import json

from zhijia_guardian.adapters import CarlaAdapter
from zhijia_guardian.benchmarks.carla_fault_injection import VARIANTS, build_carla_fault_benchmark
from zhijia_guardian.graph.diagnosis_graph import run_diagnosis_graph


def _transform(x: float, y: float) -> dict:
    return {
        "location": {"x": x, "y": y, "z": 0.0},
        "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
    }


def _actor(actor_id: int, x: float, velocity: float, *, key: bool = False) -> dict:
    return {
        "actor_id": actor_id,
        "type_id": "vehicle.tesla.model3",
        "transform": _transform(x, 0.0),
        "velocity": {"x": velocity, "y": 0.0, "z": 0.0},
        "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
        "bounding_box": {"extent": {"x": 2.4, "y": 0.95, "z": 0.75}},
        "is_key_actor": key,
    }


def _base_log() -> dict:
    frames = []
    for index in range(12):
        ego_x = min(index * 0.6, 4.2)
        ego_speed = 6.0 if index < 7 else 0.0
        target = _actor(2, 10.0, 0.0, key=True)
        frames.append(
            {
                "frame_id": 100 + index,
                "simulation_time": 20.0 + index * 0.1,
                "ego": _actor(1, ego_x, ego_speed),
                "actors": [target],
                "perception": {
                    "available": True,
                    "detection_source": "synthetic_from_annotation",
                    "detections": [
                        {
                            "track_id": "det_2",
                            "type": "vehicle",
                            "confidence": 0.92,
                            "transform": _transform(10.0, 0.0),
                            "bounding_box": target["bounding_box"],
                            "matched_actor_id": 2,
                        }
                    ],
                },
                "planning": {
                    "available": True,
                    "trajectory_source": "offline_planner",
                    "trajectory": [
                        {"dt": 0.0, "transform": _transform(ego_x, 0.0), "speed": ego_speed},
                        {"dt": 1.0, "transform": _transform(min(ego_x + 0.3, 4.5), 0.0), "speed": 0.0},
                    ],
                    "intent": "stop_for_lead_vehicle",
                    "target_speed": 6.0,
                },
                "control": {
                    "available": True,
                    "steer": 0.0,
                    "throttle": 0.35 if index < 7 else 0.0,
                    "brake": 0.8 if index >= 7 else 0.0,
                },
                "map": {"available": True, "lane_id": "1:-1", "road_id": 1, "speed_limit": 13.9},
                "events": [],
            }
        )
    return {
        "log_version": "carla_log_v0_1",
        "scenario_id": "carla_base_000001",
        "carla_version": "0.9.15",
        "map_name": "Town03",
        "fixed_delta_seconds": 0.1,
        "frames": frames,
    }


def test_carla_fault_benchmark_builds_six_isolated_variants(tmp_path):
    base_dir = tmp_path / "base"
    output_root = tmp_path / "benchmark"
    base_dir.mkdir()
    (base_dir / "base_000001.json").write_text(json.dumps(_base_log()), encoding="utf-8")

    manifest = build_carla_fault_benchmark(base_dir, output_root)

    assert manifest["num_parent_logs"] == 1
    assert manifest["num_scenarios"] == 6
    assert {row["variant"] for row in manifest["scenarios"]} == set(VARIANTS)
    assert (output_root / "canonical" / "scenarios.jsonl").exists()
    assert not (output_root / "raw" / "logs" / "manifest.json").exists()

    observed_adapter = CarlaAdapter(output_root / "raw" / "logs")
    assert all(observed_adapter.load_scenario(item).oracle is None for item in observed_adapter.list_scenarios())

    eval_adapter = CarlaAdapter(output_root / "raw" / "logs", output_root / "raw" / "labels")
    predicted = {}
    for scenario_id in eval_adapter.list_scenarios():
        scenario = eval_adapter.load_scenario(scenario_id)
        _, diagnosis = run_diagnosis_graph(scenario)
        predicted[scenario.oracle.fault_type] = diagnosis.predicted_fault_type

    assert predicted == {variant: variant for variant in VARIANTS}
