from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from zhijia_guardian.adapters.base_adapter import BaseAdapter
from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    ControlState,
    EgoState,
    EventRecord,
    FrameRecord,
    MapState,
    MetaInfo,
    PerceptionState,
    PlanningState,
    ScenarioRecord,
    SourceInfo,
    StrictModel,
)


class SafeBenchExportFrame(StrictModel):
    current_game_time: float
    ego_velocity: float = 0.0
    ego_acceleration_x: float = 0.0
    ego_acceleration_y: float = 0.0
    ego_acceleration_z: float = 0.0
    ego_x: float
    ego_y: float
    ego_z: float = 0.0
    ego_roll: float = 0.0
    ego_pitch: float = 0.0
    ego_yaw: float = 0.0
    criteria: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SafeBenchExportRecord(StrictModel):
    data_id: int
    scenario_id: int
    route_id: int
    scenario_folder: str
    frames: list[SafeBenchExportFrame]

    @model_validator(mode="after")
    def validate_frames(self) -> "SafeBenchExportRecord":
        if not self.frames:
            raise ValueError("SafeBench export record must contain at least one frame")
        timestamps = [frame.current_game_time for frame in self.frames]
        if timestamps != sorted(timestamps):
            raise ValueError("SafeBench export frames must be time-sorted")
        return self


class SafeBenchExport(StrictModel):
    format: Literal["safebench_records_v0_1"]
    scenario_category: Literal["planning"]
    safebench_commit: str
    carla_version: str
    fixed_delta_seconds: float = Field(gt=0.0)
    records: list[SafeBenchExportRecord]


class SafeBenchAdapter(BaseAdapter):
    """Read normalized SafeBench planning records without importing SafeBench."""

    def __init__(self, export_path: str | Path):
        self.export_path = Path(export_path)
        if not self.export_path.is_file():
            raise FileNotFoundError(self.export_path)
        with self.export_path.open(encoding="utf-8") as handle:
            self.export = SafeBenchExport.model_validate(json.load(handle))
        self._index = {
            self._canonical_id(record.data_id): record for record in self.export.records
        }
        if len(self._index) != len(self.export.records):
            raise ValueError("SafeBench export contains duplicate data_id values")

    @staticmethod
    def _canonical_id(data_id: int) -> str:
        return f"safebench_v0_1_{data_id:06d}"

    def list_scenarios(self) -> list[str]:
        return sorted(self._index)

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        try:
            raw = self._index[scenario_id]
        except KeyError as exc:
            raise KeyError(scenario_id) from exc

        first_time = raw.frames[0].current_game_time
        frames = [self._convert_frame(frame, first_time) for frame in raw.frames]
        return ScenarioRecord(
            scenario_id=scenario_id,
            source=SourceInfo(
                dataset="safebench",
                version="records_v0_1",
                raw_log_id=str(raw.data_id),
                raw_tokens={
                    "data_id": raw.data_id,
                    "scenario_id": raw.scenario_id,
                    "route_id": raw.route_id,
                    "scenario_folder": raw.scenario_folder,
                    "safebench_commit": self.export.safebench_commit,
                    "carla_version": self.export.carla_version,
                },
            ),
            meta=MetaInfo(
                coordinate_frame="world",
                frequency_hz=1.0 / self.export.fixed_delta_seconds,
                duration=frames[-1].timestamp,
            ),
            frames=frames,
            events_observed=self._events(raw.frames, first_time),
            oracle=None,
        )

    @staticmethod
    def _convert_frame(frame: SafeBenchExportFrame, first_time: float) -> FrameRecord:
        yaw = math.radians(frame.ego_yaw)
        return FrameRecord(
            timestamp=frame.current_game_time - first_time,
            ego=EgoState(
                x=frame.ego_x,
                y=frame.ego_y,
                yaw=yaw,
                vx=frame.ego_velocity * math.cos(yaw),
                vy=frame.ego_velocity * math.sin(yaw),
                ax=frame.ego_acceleration_x,
                ay=frame.ego_acceleration_y,
            ),
            actors_gt=[],
            actors_gt_source=ActorGtSource.UNAVAILABLE,
            perception=PerceptionState(available=False),
            planning=PlanningState(available=False),
            control=ControlState(available=False),
            map=MapState(available=False),
        )

    @classmethod
    def _events(
        cls,
        frames: list[SafeBenchExportFrame],
        first_time: float,
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        previous: dict[str, str | int | float | bool | None] = {}
        for frame in frames:
            for criterion, value in frame.criteria.items():
                old_value = previous.get(criterion)
                if cls._is_new_failure(value, old_value):
                    events.append(
                        EventRecord(
                            event_type=f"safebench_{criterion}",
                            timestamp=frame.current_game_time - first_time,
                            description=f"SafeBench criterion {criterion} entered a failure state.",
                            attributes={"criterion": criterion, "value": value},
                        )
                    )
                previous[criterion] = value
        return events

    @staticmethod
    def _is_new_failure(value: Any, old_value: Any) -> bool:
        if isinstance(value, str):
            return value.lower() in {"failure", "failed"} and value != old_value
        if isinstance(value, bool):
            return value and not bool(old_value)
        return False
