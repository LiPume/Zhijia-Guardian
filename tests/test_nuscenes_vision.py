from pathlib import Path

import pytest

from zhijia_guardian.adapters import NuScenesVisionAdapter
from zhijia_guardian.benchmarks.nuscenes_vision import summarize_distance_bucket_metrics
from zhijia_guardian.experiments.run_diagnosis import run_unlabeled_diagnosis
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.schemas.nuscenes_vision import (
    NuScenesVisionClip,
    NuScenesVisionFrame,
    VisionFrameMetrics,
)
from zhijia_guardian.schemas.scenario import ActorState, Detection, DetectionSource, EgoState
from zhijia_guardian.utils.io import dump_scenario_jsonl


REAL_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1")


def _write_clip(root: Path) -> str:
    scenario_id = "nuscenes_real_v0_1_000001"
    actor = ActorState(
        actor_id="vehicle_1",
        type="car",
        x=10.0,
        y=2.0,
        is_key_actor=True,
        sensor_bbox_xyxy=(100.0, 100.0, 200.0, 200.0),
        sensor_channel="CAM_FRONT",
    )
    matched = Detection(
        track_id="vehicle_1",
        type="car",
        confidence=0.9,
        x=10.0,
        y=2.0,
        matched_gt_id="vehicle_1",
        bbox_xyxy=(102.0, 101.0, 198.0, 199.0),
        sensor_channel="CAM_FRONT",
        model_class="car",
        association_iou=0.9,
    )
    unmatched = Detection(
        track_id="det_2",
        type="person",
        confidence=0.7,
        bbox_xyxy=(300.0, 100.0, 340.0, 220.0),
        sensor_channel="CAM_FRONT",
        model_class="person",
    )
    metrics = VisionFrameMetrics(
        visible_gt=1,
        key_actors=1,
        detections=2,
        matched=1,
        matched_key_actors=1,
        class_correct=1,
        false_positives=1,
        missed_key_actors=0,
    )
    clip = NuScenesVisionClip(
        scenario_id=scenario_id,
        scene_name="scene-test",
        scene_token="scene_token",
        detector_name="yolov8n",
        detector_weights="weights.pt",
        detector_confidence=0.25,
        association_iou_threshold=0.3,
        frames=[
            NuScenesVisionFrame(
                timestamp=0.0,
                sample_token="sample_1",
                sample_data_token="camera_1",
                image_path="image.jpg",
                image_width=1600,
                image_height=900,
                ego=EgoState(x=0.0, y=0.0),
                actors_gt=[actor],
                detections=[matched, unmatched],
                metrics=metrics,
            )
        ],
    )
    root.mkdir(parents=True)
    (root / f"{scenario_id}.json").write_text(clip.model_dump_json(indent=2))
    return scenario_id


def test_nuscenes_vision_adapter_preserves_2d_only_detections(tmp_path):
    scenario_id = _write_clip(tmp_path / "clips")
    record = NuScenesVisionAdapter(tmp_path / "clips").load_scenario(scenario_id)

    assert record.oracle is None
    assert record.frames[0].perception.detection_source == DetectionSource.MODEL_OUTPUT
    assert record.frames[0].perception.detections[1].x is None
    assert record.frames[0].planning.available is False
    assert "oracle" not in record.observed_view()


def test_nuscenes_vision_adapter_accepts_versioned_side_camera(tmp_path):
    scenario_id = _write_clip(tmp_path / "clips")
    path = tmp_path / "clips" / f"{scenario_id}.json"
    clip = NuScenesVisionClip.model_validate_json(path.read_text())
    payload = clip.model_dump(mode="json")
    payload["benchmark_version"] = "v0_2"
    payload["sensor_channel"] = "CAM_BACK_LEFT"
    path.write_text(NuScenesVisionClip.model_validate(payload).model_dump_json(indent=2))

    record = NuScenesVisionAdapter(tmp_path / "clips").load_scenario(scenario_id)

    assert record.source.version == "v0_2"
    assert record.source.raw_tokens["sensor_channel"] == "CAM_BACK_LEFT"
    assert "CAM_BACK_LEFT" in record.events_observed[0].description


def test_distance_bucket_metrics_are_computed_from_world_distance(tmp_path):
    _write_clip(tmp_path / "clips")

    metrics = summarize_distance_bucket_metrics(tmp_path / "clips")

    near = metrics["aggregate"]["0-20m"]
    assert near["visible_gt"] == 1
    assert near["matched"] == 1
    assert near["annotation_recall"] == 1.0
    assert metrics["aggregate"]["20-40m"]["visible_gt"] == 0


def test_unlabeled_runner_writes_hypotheses_without_accuracy(tmp_path):
    scenario_id = _write_clip(tmp_path / "clips")
    record = NuScenesVisionAdapter(tmp_path / "clips").load_scenario(scenario_id)
    dataset = tmp_path / "scenarios.jsonl"
    dump_scenario_jsonl([record], dataset)

    run_dir = run_unlabeled_diagnosis(dataset, "real_smoke", output_root=tmp_path / "runs")

    summary = (run_dir / "summary.json").read_text()
    assert '"accuracy_metrics_available": false' in summary
    assert (run_dir / "reports" / f"{scenario_id}.md").is_file()
    assert not (run_dir / "eval.csv").exists()


@pytest.mark.skipif(not REAL_ROOT.exists(), reason="nuScenes YOLO benchmark not generated")
def test_real_nuscenes_vision_graph_smoke():
    adapter = NuScenesVisionAdapter(REAL_ROOT / "raw" / "clips")
    assert len(adapter.list_scenarios()) == 5
    record = adapter.load_scenario(adapter.list_scenarios()[0])

    assert record.oracle is None
    assert len(record.frames) == 40
    assert any(detection.x is None for frame in record.frames for detection in frame.perception.detections)
    _, diagnosis = run_diagnosis_graph(record)
    assert diagnosis.predicted_fault_type == "perception_miss"
    skipped = {step.agent_name for step in diagnosis.agent_trace if step.status == "skipped"}
    assert skipped == {"planning_agent", "control_agent"}
