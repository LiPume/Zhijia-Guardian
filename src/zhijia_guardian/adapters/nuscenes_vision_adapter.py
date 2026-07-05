from __future__ import annotations

from pathlib import Path

from zhijia_guardian.adapters.base_adapter import BaseAdapter
from zhijia_guardian.schemas.nuscenes_vision import NuScenesVisionClip
from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    ControlState,
    DetectionSource,
    EventRecord,
    FrameRecord,
    MapState,
    MetaInfo,
    PerceptionState,
    PlanningState,
    ScenarioRecord,
    SourceInfo,
)


class NuScenesVisionAdapter(BaseAdapter):
    """Read versioned nuScenes camera + detector clip exports."""

    def __init__(self, clip_root: str | Path):
        self.clip_root = Path(clip_root)
        if not self.clip_root.exists():
            raise FileNotFoundError(self.clip_root)
        self._paths = {
            path.stem: path
            for path in sorted(self.clip_root.glob("*.json"))
            if path.name != "manifest.json"
        }

    def list_scenarios(self) -> list[str]:
        return sorted(self._paths)

    def load_clip(self, scenario_id: str) -> NuScenesVisionClip:
        try:
            path = self._paths[scenario_id]
        except KeyError as exc:
            raise KeyError(scenario_id) from exc
        clip = NuScenesVisionClip.model_validate_json(path.read_text(encoding="utf-8"))
        if clip.scenario_id != scenario_id:
            raise ValueError(
                f"clip scenario_id {clip.scenario_id} does not match filename {scenario_id}"
            )
        return clip

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        clip = self.load_clip(scenario_id)
        frames = [
            FrameRecord(
                timestamp=frame.timestamp,
                ego=frame.ego,
                actors_gt=frame.actors_gt,
                actors_gt_source=(
                    ActorGtSource.DATASET_ANNOTATION
                    if frame.actors_gt
                    else ActorGtSource.UNAVAILABLE
                ),
                perception=PerceptionState(
                    available=True,
                    detection_source=DetectionSource.MODEL_OUTPUT,
                    detections=frame.detections,
                ),
                planning=PlanningState(available=False),
                control=ControlState(available=False),
                map=MapState(available=False),
            )
            for frame in clip.frames
        ]
        return ScenarioRecord(
            scenario_id=clip.scenario_id,
            source=SourceInfo(
                dataset="nuscenes_yolo",
                version=clip.benchmark_version,
                raw_log_id=clip.scene_name,
                raw_tokens={
                    "scene_token": clip.scene_token,
                    "sensor_channel": clip.sensor_channel,
                    "detector_name": clip.detector_name,
                    "clip_path": str(self._paths[scenario_id]),
                },
            ),
            meta=MetaInfo(
                coordinate_frame="world",
                frequency_hz=_frequency_hz(clip),
                duration=clip.frames[-1].timestamp,
            ),
            frames=frames,
            events_observed=[
                EventRecord(
                    event_type="dataset_context",
                    timestamp=0.0,
                    description=(
                        f"Real nuScenes {clip.sensor_channel} clip with frozen YOLO "
                        "detector output."
                    ),
                    attributes={
                        "scene_name": clip.scene_name,
                        "sensor_channel": clip.sensor_channel,
                        "detector_name": clip.detector_name,
                        "oracle_available": False,
                    },
                ),
                EventRecord(
                    event_type="association_context",
                    timestamp=0.0,
                    description="2D detector boxes are associated with projected dataset annotations for offline evaluation.",
                    attributes={
                        "iou_threshold": clip.association_iou_threshold,
                        "world_position_source": "matched_dataset_annotation",
                    },
                ),
            ],
            oracle=None,
        )


def _frequency_hz(clip: NuScenesVisionClip) -> float:
    if len(clip.frames) < 2:
        return 2.0
    deltas = [
        right.timestamp - left.timestamp
        for left, right in zip(clip.frames, clip.frames[1:])
        if right.timestamp > left.timestamp
    ]
    if not deltas:
        return 2.0
    return 1.0 / (sum(deltas) / len(deltas))
