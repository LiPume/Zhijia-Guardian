from pathlib import Path

import pytest

from zhijia_guardian.agents.visual_review_agent import (
    VisualGeneration,
    VisualReviewConfig,
    build_visual_review_content,
    run_visual_review_agent,
    select_visual_frames,
)
from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.nuscenes_vision import (
    NuScenesVisionClip,
    NuScenesVisionFrame,
    VisionFrameMetrics,
)
from zhijia_guardian.schemas.scenario import EgoState
from zhijia_guardian.schemas.visual_review import (
    VisualCondition,
    VisualObservation,
    VisualReviewOutput,
)


class FakeVisualClient:
    def __init__(self, output: VisualReviewOutput):
        self.output = output
        self.content = None

    def review(self, content):
        self.content = content
        return VisualGeneration(output=self.output, metadata={"response_id": "fake"})


def _clip(tmp_path: Path, frame_count: int = 5) -> NuScenesVisionClip:
    frames = []
    metrics = VisionFrameMetrics(
        visible_gt=0,
        key_actors=0,
        detections=0,
        matched=0,
        matched_key_actors=0,
        class_correct=0,
        false_positives=0,
        missed_key_actors=0,
    )
    for index in range(frame_count):
        path = tmp_path / f"raw_{index}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        frames.append(
            NuScenesVisionFrame(
                timestamp=index * 0.5,
                sample_token=f"sample_{index}",
                sample_data_token=f"camera_{index}",
                image_path=str(path),
                image_width=1600,
                image_height=900,
                ego=EgoState(x=0.0, y=0.0),
                metrics=metrics,
            )
        )
    return NuScenesVisionClip(
        scenario_id="nuscenes_real_v0_1_000001",
        scene_name="scene-test",
        scene_token="scene-token",
        detector_name="yolov8n",
        detector_weights="weights.pt",
        detector_confidence=0.25,
        association_iou_threshold=0.3,
        frames=frames,
    )


def _metrics() -> MetricsRecord:
    return MetricsRecord(
        scenario_id="nuscenes_real_v0_1_000001",
        evidence=[
            EvidenceRecord(
                evidence_id="E_PER_001",
                metric_name="missed_key_actors",
                value=3,
                threshold=0,
                time=0.5,
                status="violation",
            )
        ],
    )


def _output(evidence_ids=None) -> VisualReviewOutput:
    return VisualReviewOutput(
        conditions=VisualCondition(
            lighting="daylight",
            weather="clear",
            visibility="good",
            road_context="Urban road",
        ),
        observations=[
            VisualObservation(
                observation_id="V_001",
                category="occlusion",
                description="A vehicle is partially occluded.",
                confidence=0.7,
                frame_indices=[0],
                related_evidence_ids=evidence_ids or [],
            )
        ],
        suspected_fault_type="uncertain",
        confidence=0.4,
        assessment="Pixels alone do not establish a detector fault.",
        limitations=["Only sampled front-camera frames were reviewed."],
    )


def test_direct_vlm_input_excludes_tool_and_annotation_context(tmp_path):
    clip = _clip(tmp_path)
    config = VisualReviewConfig(mode="direct_vlm", max_frames=3)
    selected = select_visual_frames(clip, config.max_frames)
    content = build_visual_review_content(clip, _metrics(), selected, config)
    text = "\n".join(item["text"] for item in content if item["type"] == "text")

    assert selected == [0, 2, 4]
    assert "tool_evidence" not in text
    assert "actors_gt" not in text
    assert "annotation" in text
    assert sum(item["type"] == "image_url" for item in content) == 3


def test_visual_review_agent_returns_versioned_observed_only_record(tmp_path):
    clip = _clip(tmp_path)
    client = FakeVisualClient(_output())
    config = VisualReviewConfig(mode="direct_vlm", max_frames=2)

    record = run_visual_review_agent(clip, _metrics(), config, client)

    assert record.schema_version == "visual_review_v1"
    assert record.oracle_used is False
    assert record.annotation_images_used is False
    assert record.method == "direct_vlm"
    assert len(record.sampled_frames) == 2
    assert client.content is not None


def test_tools_mode_allows_only_known_evidence_ids(tmp_path):
    clip = _clip(tmp_path)
    config = VisualReviewConfig(mode="vlm_with_tools", max_frames=2)
    valid = FakeVisualClient(_output(["E_PER_001"]))
    assert run_visual_review_agent(clip, _metrics(), config, valid).method == "vlm_with_tools"

    invalid = FakeVisualClient(_output(["E_UNKNOWN"]))
    with pytest.raises(ValueError, match="unknown evidence"):
        run_visual_review_agent(clip, _metrics(), config, invalid)
