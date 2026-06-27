from __future__ import annotations

import json
from math import radians
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from zhijia_guardian.adapters.base_adapter import BaseAdapter
from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    ActorState,
    ControlState,
    Detection,
    DetectionSource,
    EgoState,
    EventRecord,
    FrameRecord,
    MapState,
    MetaInfo,
    OracleRecord,
    PerceptionState,
    PlanningState,
    ScenarioRecord,
    SourceInfo,
    StrictModel,
    TrajectoryPoint,
    TrajectorySource,
)


class CarlaVector3D(StrictModel):
    x: float
    y: float
    z: float = 0.0


class CarlaRotation(StrictModel):
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0


class CarlaTransform(StrictModel):
    location: CarlaVector3D
    rotation: CarlaRotation = Field(default_factory=CarlaRotation)


class CarlaBoundingBox(StrictModel):
    extent: CarlaVector3D


class CarlaActorSnapshot(StrictModel):
    actor_id: int
    type_id: str
    transform: CarlaTransform
    velocity: CarlaVector3D = Field(default_factory=lambda: CarlaVector3D(x=0.0, y=0.0))
    acceleration: CarlaVector3D = Field(default_factory=lambda: CarlaVector3D(x=0.0, y=0.0))
    bounding_box: CarlaBoundingBox
    is_key_actor: bool = False


class CarlaDetectionSnapshot(StrictModel):
    track_id: str
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    transform: CarlaTransform
    bounding_box: CarlaBoundingBox
    matched_actor_id: int | None = None


class CarlaPerceptionSnapshot(StrictModel):
    available: bool = False
    detection_source: DetectionSource = DetectionSource.UNAVAILABLE
    detections: list[CarlaDetectionSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_availability(self) -> "CarlaPerceptionSnapshot":
        if not self.available and self.detections:
            raise ValueError("detections must be empty when perception is unavailable")
        if self.available and self.detection_source == DetectionSource.UNAVAILABLE:
            raise ValueError("detection_source is required when perception is available")
        return self


class CarlaTrajectoryPoint(StrictModel):
    dt: float
    transform: CarlaTransform
    speed: float | None = None


class CarlaPlanningSnapshot(StrictModel):
    available: bool = False
    trajectory_source: TrajectorySource = TrajectorySource.UNAVAILABLE
    trajectory: list[CarlaTrajectoryPoint] = Field(default_factory=list)
    intent: str | None = None
    target_speed: float | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> "CarlaPlanningSnapshot":
        if not self.available and self.trajectory:
            raise ValueError("trajectory must be empty when planning is unavailable")
        if self.available and self.trajectory_source == TrajectorySource.UNAVAILABLE:
            raise ValueError("trajectory_source is required when planning is available")
        return self


class CarlaControlSnapshot(StrictModel):
    available: bool = False
    steer: float | None = None
    throttle: float | None = None
    brake: float | None = None


class CarlaMapSnapshot(StrictModel):
    available: bool = False
    lane_id: str | None = None
    road_id: int | None = None
    speed_limit: float | None = None


class CarlaRawEvent(StrictModel):
    event_type: str
    description: str = ""
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CarlaFrameSnapshot(StrictModel):
    frame_id: int
    simulation_time: float
    ego: CarlaActorSnapshot
    actors: list[CarlaActorSnapshot] = Field(default_factory=list)
    perception: CarlaPerceptionSnapshot = Field(default_factory=CarlaPerceptionSnapshot)
    planning: CarlaPlanningSnapshot = Field(default_factory=CarlaPlanningSnapshot)
    control: CarlaControlSnapshot = Field(default_factory=CarlaControlSnapshot)
    map: CarlaMapSnapshot = Field(default_factory=CarlaMapSnapshot)
    events: list[CarlaRawEvent] = Field(default_factory=list)


class CarlaRawLog(StrictModel):
    log_version: Literal["carla_log_v0_1"]
    scenario_id: str
    carla_version: str
    map_name: str
    fixed_delta_seconds: float = Field(gt=0.0)
    frames: list[CarlaFrameSnapshot]

    @model_validator(mode="after")
    def validate_frames(self) -> "CarlaRawLog":
        if not self.frames:
            raise ValueError("CARLA log must contain at least one frame")
        timestamps = [frame.simulation_time for frame in self.frames]
        if timestamps != sorted(timestamps):
            raise ValueError("CARLA frames must be sorted by simulation_time")
        return self


class CarlaLabelFile(StrictModel):
    scenario_id: str
    oracle: OracleRecord


class CarlaAdapter(BaseAdapter):
    """Convert versioned CARLA JSON logs into the canonical scenario schema."""

    def __init__(self, log_dir: str | Path, label_dir: str | Path | None = None):
        self.log_dir = Path(log_dir)
        self.label_dir = Path(label_dir) if label_dir is not None else None
        if not self.log_dir.exists():
            raise FileNotFoundError(self.log_dir)
        self._index = self._build_index()

    def _build_index(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for path in sorted(self.log_dir.glob("*.json")):
            raw = self._load_raw(path)
            if raw.scenario_id in index:
                raise ValueError(f"duplicate CARLA scenario_id: {raw.scenario_id}")
            index[raw.scenario_id] = path
        return index

    def list_scenarios(self) -> list[str]:
        return sorted(self._index)

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        try:
            path = self._index[scenario_id]
        except KeyError as exc:
            raise KeyError(scenario_id) from exc
        raw = self._load_raw(path)
        first_time = raw.frames[0].simulation_time
        frames = [self._convert_frame(frame, first_time) for frame in raw.frames]
        events = [
            EventRecord(
                event_type=event.event_type,
                timestamp=frame.simulation_time - first_time,
                description=event.description,
                attributes=event.attributes,
            )
            for frame in raw.frames
            for event in frame.events
        ]
        return ScenarioRecord(
            scenario_id=raw.scenario_id,
            source=SourceInfo(
                dataset="carla",
                version=raw.carla_version,
                raw_log_id=path.stem,
                raw_tokens={
                    "log_path": str(path),
                    "map_name": raw.map_name,
                    "first_frame_id": raw.frames[0].frame_id,
                    "last_frame_id": raw.frames[-1].frame_id,
                },
            ),
            meta=MetaInfo(
                coordinate_frame="world",
                frequency_hz=1.0 / raw.fixed_delta_seconds,
                duration=frames[-1].timestamp,
            ),
            frames=frames,
            events_observed=events,
            oracle=self._load_oracle(raw.scenario_id),
        )

    @staticmethod
    def _load_raw(path: Path) -> CarlaRawLog:
        with path.open("r", encoding="utf-8") as f:
            return CarlaRawLog.model_validate(json.load(f))

    def _load_oracle(self, scenario_id: str) -> OracleRecord | None:
        if self.label_dir is None:
            return None
        path = self.label_dir / f"{scenario_id}.label.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            label = CarlaLabelFile.model_validate(json.load(f))
        if label.scenario_id != scenario_id:
            raise ValueError(f"CARLA label scenario_id mismatch: {path}")
        return label.oracle

    def _convert_frame(self, frame: CarlaFrameSnapshot, first_time: float) -> FrameRecord:
        actors = [self._convert_actor(actor) for actor in frame.actors]
        perception = frame.perception
        planning = frame.planning
        return FrameRecord(
            timestamp=frame.simulation_time - first_time,
            ego=self._convert_ego(frame.ego),
            actors_gt=actors,
            actors_gt_source=ActorGtSource.SIMULATION if actors else ActorGtSource.UNAVAILABLE,
            perception=PerceptionState(
                available=perception.available,
                detection_source=perception.detection_source,
                detections=[self._convert_detection(item) for item in perception.detections],
            ),
            planning=PlanningState(
                available=planning.available,
                trajectory_source=planning.trajectory_source,
                trajectory=[
                    TrajectoryPoint(
                        dt=point.dt,
                        x=point.transform.location.x,
                        y=point.transform.location.y,
                        yaw=radians(point.transform.rotation.yaw),
                        speed=point.speed,
                    )
                    for point in planning.trajectory
                ],
                intent=planning.intent,
                target_speed=planning.target_speed,
            ),
            control=ControlState(**frame.control.model_dump()),
            map=MapState(
                available=frame.map.available,
                lane_id=frame.map.lane_id,
                speed_limit=frame.map.speed_limit,
                roadblock_ids=[str(frame.map.road_id)] if frame.map.road_id is not None else [],
            ),
        )

    @staticmethod
    def _actor_type(type_id: str) -> str:
        if type_id.startswith("vehicle."):
            return "vehicle"
        if type_id.startswith("walker.pedestrian."):
            return "pedestrian"
        return type_id.split(".", maxsplit=1)[0]

    @classmethod
    def _convert_actor(cls, actor: CarlaActorSnapshot) -> ActorState:
        return ActorState(
            actor_id=str(actor.actor_id),
            type=cls._actor_type(actor.type_id),
            x=actor.transform.location.x,
            y=actor.transform.location.y,
            yaw=radians(actor.transform.rotation.yaw),
            vx=actor.velocity.x,
            vy=actor.velocity.y,
            length=2.0 * actor.bounding_box.extent.x,
            width=2.0 * actor.bounding_box.extent.y,
            height=2.0 * actor.bounding_box.extent.z,
            is_key_actor=actor.is_key_actor,
        )

    @staticmethod
    def _convert_ego(actor: CarlaActorSnapshot) -> EgoState:
        return EgoState(
            x=actor.transform.location.x,
            y=actor.transform.location.y,
            yaw=radians(actor.transform.rotation.yaw),
            vx=actor.velocity.x,
            vy=actor.velocity.y,
            ax=actor.acceleration.x,
            ay=actor.acceleration.y,
            length=2.0 * actor.bounding_box.extent.x,
            width=2.0 * actor.bounding_box.extent.y,
        )

    @staticmethod
    def _convert_detection(detection: CarlaDetectionSnapshot) -> Detection:
        return Detection(
            track_id=detection.track_id,
            type=detection.type,
            confidence=detection.confidence,
            x=detection.transform.location.x,
            y=detection.transform.location.y,
            yaw=radians(detection.transform.rotation.yaw),
            length=2.0 * detection.bounding_box.extent.x,
            width=2.0 * detection.bounding_box.extent.y,
            matched_gt_id=str(detection.matched_actor_id) if detection.matched_actor_id is not None else None,
        )
