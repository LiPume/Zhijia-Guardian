from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from zhijia_guardian.schemas.scenario import ActorState, Detection, EgoState, StrictModel


class VisionFrameMetrics(StrictModel):
    visible_gt: int = Field(ge=0)
    key_actors: int = Field(ge=0)
    detections: int = Field(ge=0)
    matched: int = Field(ge=0)
    matched_key_actors: int = Field(ge=0)
    class_correct: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    missed_key_actors: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "VisionFrameMetrics":
        if self.key_actors > self.visible_gt:
            raise ValueError("key_actors cannot exceed visible_gt")
        if self.matched > min(self.visible_gt, self.detections):
            raise ValueError("matched cannot exceed visible_gt or detections")
        if self.matched_key_actors > min(self.key_actors, self.matched):
            raise ValueError("matched_key_actors cannot exceed key_actors or matched")
        if self.class_correct > self.matched:
            raise ValueError("class_correct cannot exceed matched")
        if self.false_positives != self.detections - self.matched:
            raise ValueError("false_positives must equal detections - matched")
        if self.missed_key_actors != self.key_actors - self.matched_key_actors:
            raise ValueError("missed_key_actors must equal key_actors - matched_key_actors")
        return self


class NuScenesVisionFrame(StrictModel):
    timestamp: float = Field(ge=0.0)
    sample_token: str
    sample_data_token: str
    image_path: str
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    ego: EgoState
    actors_gt: list[ActorState] = Field(default_factory=list)
    detections: list[Detection] = Field(default_factory=list)
    metrics: VisionFrameMetrics


class NuScenesVisionClip(StrictModel):
    schema_version: Literal["nuscenes_vision_clip_v1"] = "nuscenes_vision_clip_v1"
    scenario_id: str
    scene_name: str
    scene_token: str
    sensor_channel: Literal["CAM_FRONT"] = "CAM_FRONT"
    detector_name: str
    detector_weights: str
    detector_confidence: float = Field(ge=0.0, le=1.0)
    association_iou_threshold: float = Field(ge=0.0, le=1.0)
    frames: list[NuScenesVisionFrame]

    @model_validator(mode="after")
    def validate_frames(self) -> "NuScenesVisionClip":
        if not self.frames:
            raise ValueError("vision clip must contain at least one frame")
        timestamps = [frame.timestamp for frame in self.frames]
        if timestamps != sorted(timestamps):
            raise ValueError("vision clip frames must be sorted")
        return self
