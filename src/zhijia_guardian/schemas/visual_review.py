from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from zhijia_guardian.schemas.scenario import StrictModel


VisualFaultType = Literal[
    "normal",
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "perception_class_confusion",
    "uncertain",
]


class VisualCondition(StrictModel):
    lighting: Literal["daylight", "night", "mixed", "uncertain"]
    weather: Literal["clear", "rain", "fog", "snow", "mixed", "uncertain"]
    visibility: Literal["good", "moderate", "poor", "uncertain"]
    road_context: str


class VisualObservation(StrictModel):
    observation_id: str
    category: Literal[
        "road_user",
        "occlusion",
        "visibility",
        "possible_miss",
        "possible_false_positive",
        "class_ambiguity",
        "temporal_change",
        "other",
    ]
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    frame_indices: list[int] = Field(min_length=1)
    related_evidence_ids: list[str] = Field(default_factory=list)


class VisualReviewOutput(StrictModel):
    conditions: VisualCondition
    observations: list[VisualObservation] = Field(default_factory=list)
    suspected_fault_type: VisualFaultType
    confidence: float = Field(ge=0.0, le=1.0)
    assessment: str
    limitations: list[str] = Field(min_length=1)


class VisualSampleFrame(StrictModel):
    frame_index: int = Field(ge=0)
    timestamp: float = Field(ge=0.0)
    image_path: str
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VisualReviewRecord(StrictModel):
    schema_version: Literal["visual_review_v1"] = "visual_review_v1"
    scenario_id: str
    method: Literal["direct_vlm", "vlm_with_tools"]
    provider: str
    model: str
    oracle_used: Literal[False] = False
    annotation_images_used: Literal[False] = False
    sampled_frames: list[VisualSampleFrame] = Field(min_length=1)
    output: VisualReviewOutput
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "VisualReviewRecord":
        valid_indices = {frame.frame_index for frame in self.sampled_frames}
        observation_ids = [item.observation_id for item in self.output.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("visual observation_id values must be unique")
        for observation in self.output.observations:
            unknown = set(observation.frame_indices) - valid_indices
            if unknown:
                raise ValueError(f"visual observation references unsampled frames: {sorted(unknown)}")
        return self
