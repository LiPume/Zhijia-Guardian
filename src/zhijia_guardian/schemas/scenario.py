from __future__ import annotations

from enum import Enum
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


LABEL_LEAK_KEYWORDS = (
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "planning_collision_risk",
    "control_delay",
    "root_module",
    "fault_type",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ActorGtSource(str, Enum):
    SIMULATION = "simulation"
    DATASET_ANNOTATION = "dataset_annotation"
    OFFLINE_RECONSTRUCTION = "offline_reconstruction"
    UNAVAILABLE = "unavailable"


class DetectionSource(str, Enum):
    MODEL_OUTPUT = "model_output"
    SYNTHETIC_FROM_ANNOTATION = "synthetic_from_annotation"
    DATASET_PREDICTION = "dataset_prediction"
    UNAVAILABLE = "unavailable"


class TrajectorySource(str, Enum):
    EXPERT_FUTURE = "expert_future"
    OFFLINE_PLANNER = "offline_planner"
    PERTURBED_PLANNER = "perturbed_planner"
    MODEL_PREDICTION = "model_prediction"
    UNAVAILABLE = "unavailable"

    @property
    def diagnosable(self) -> bool:
        return self in {
            TrajectorySource.OFFLINE_PLANNER,
            TrajectorySource.PERTURBED_PLANNER,
            TrajectorySource.MODEL_PREDICTION,
        }


class SourceInfo(StrictModel):
    dataset: str
    version: str
    raw_log_id: str | None = None
    raw_tokens: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)


class MetaInfo(StrictModel):
    coordinate_frame: Literal["world", "ego"] = "world"
    distance_unit: Literal["meter"] = "meter"
    time_unit: Literal["second"] = "second"
    speed_unit: Literal["m/s"] = "m/s"
    angle_unit: Literal["radian"] = "radian"
    frequency_hz: float
    duration: float

    @field_validator("frequency_hz")
    @classmethod
    def frequency_positive(cls, value: float) -> float:
        if value <= 0 or not isfinite(value):
            raise ValueError("frequency_hz must be positive")
        return value

    @field_validator("duration")
    @classmethod
    def duration_non_negative(cls, value: float) -> float:
        if value < 0 or not isfinite(value):
            raise ValueError("duration must be non-negative")
        return value


class EgoState(StrictModel):
    x: float
    y: float
    yaw: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    length: float = Field(default=4.8, gt=0.0)
    width: float = Field(default=1.9, gt=0.0)
    lane_id: str | None = None


class ActorState(StrictModel):
    actor_id: str
    type: str
    x: float
    y: float
    yaw: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    length: float = 0.0
    width: float = 0.0
    height: float | None = None
    is_key_actor: bool = False
    sensor_bbox_xyxy: tuple[float, float, float, float] | None = None
    sensor_channel: str | None = None

    @model_validator(mode="after")
    def validate_sensor_bbox(self) -> "ActorState":
        _validate_xyxy(self.sensor_bbox_xyxy, "actor sensor_bbox_xyxy")
        return self


class Detection(StrictModel):
    track_id: str
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    x: float | None = None
    y: float | None = None
    yaw: float = 0.0
    length: float = 0.0
    width: float = 0.0
    matched_gt_id: str | None = None
    bbox_xyxy: tuple[float, float, float, float] | None = None
    sensor_channel: str | None = None
    model_class: str | None = None
    association_iou: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bbox(self) -> "Detection":
        _validate_xyxy(self.bbox_xyxy, "detection bbox_xyxy")
        return self


class PerceptionState(StrictModel):
    available: bool = False
    detection_source: DetectionSource = DetectionSource.UNAVAILABLE
    detections: list[Detection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_availability(self) -> "PerceptionState":
        if not self.available and self.detections:
            raise ValueError("perception.detections must be empty when perception.available=false")
        if self.available and self.detection_source == DetectionSource.UNAVAILABLE:
            raise ValueError("perception.detection_source must be set when perception.available=true")
        return self


class TrajectoryPoint(StrictModel):
    dt: float
    x: float
    y: float
    yaw: float | None = None
    speed: float | None = None


class PlanningState(StrictModel):
    available: bool = False
    trajectory_source: TrajectorySource = TrajectorySource.UNAVAILABLE
    trajectory: list[TrajectoryPoint] = Field(default_factory=list)
    intent: str | None = None
    target_speed: float | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "PlanningState":
        if not self.available:
            if self.trajectory:
                raise ValueError("planning.trajectory must be empty when planning.available=false")
            if self.trajectory_source != TrajectorySource.UNAVAILABLE:
                raise ValueError("planning.trajectory_source must be unavailable when planning.available=false")
        if self.available and self.trajectory_source == TrajectorySource.UNAVAILABLE:
            raise ValueError("planning.trajectory_source must be set when planning.available=true")
        return self


class ControlState(StrictModel):
    available: bool = False
    steer: float | None = None
    throttle: float | None = None
    brake: float | None = None


class MapState(StrictModel):
    available: bool = False
    lane_id: str | None = None
    drivable_area: Any = None
    speed_limit: float | None = None
    roadblock_ids: list[str] = Field(default_factory=list)


class FrameRecord(StrictModel):
    timestamp: float
    ego: EgoState
    actors_gt: list[ActorState] = Field(default_factory=list)
    actors_gt_source: ActorGtSource = ActorGtSource.UNAVAILABLE
    perception: PerceptionState = Field(default_factory=PerceptionState)
    planning: PlanningState = Field(default_factory=PlanningState)
    control: ControlState = Field(default_factory=ControlState)
    map: MapState = Field(default_factory=MapState)

    @model_validator(mode="after")
    def validate_actor_source(self) -> "FrameRecord":
        if self.actors_gt and self.actors_gt_source == ActorGtSource.UNAVAILABLE:
            raise ValueError("actors_gt_source must be set when actors_gt is not empty")
        return self


class EventRecord(StrictModel):
    event_type: str
    timestamp: float
    description: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class OracleRecord(StrictModel):
    visible_to_diagnosis: Literal[False] = False
    fault_type: str | None = None
    root_module: str | None = None
    fault_start_time: float | None = None
    fault_segment: tuple[float, float] | None = None
    notes: str | None = None


class ScenarioRecord(StrictModel):
    scenario_id: str
    source: SourceInfo
    meta: MetaInfo
    frames: list[FrameRecord]
    events_observed: list[EventRecord] = Field(default_factory=list)
    oracle: OracleRecord | None = None

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_must_not_leak_label(cls, value: str) -> str:
        lowered = value.lower()
        for keyword in LABEL_LEAK_KEYWORDS:
            if keyword in lowered:
                raise ValueError(f"scenario_id leaks label keyword: {keyword}")
        return value

    @model_validator(mode="after")
    def validate_timestamps(self) -> "ScenarioRecord":
        if not self.frames:
            raise ValueError("ScenarioRecord.frames must not be empty")
        timestamps = [frame.timestamp for frame in self.frames]
        if timestamps != sorted(timestamps):
            raise ValueError("frames must be sorted by timestamp")
        return self

    def observed_view(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"oracle": True, "source": {"generation": True}})

    def load_oracle_for_eval(self) -> OracleRecord | None:
        return self.oracle


def _validate_xyxy(
    bbox: tuple[float, float, float, float] | None,
    field_name: str,
) -> None:
    if bbox is None:
        return
    x1, y1, x2, y2 = bbox
    if not all(isfinite(value) for value in bbox):
        raise ValueError(f"{field_name} must contain finite values")
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"{field_name} must satisfy x2>x1 and y2>y1")
