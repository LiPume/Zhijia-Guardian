from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord, TrajectorySource
from zhijia_guardian.tools.evidence import EvidenceFactory
from zhijia_guardian.utils.geometry import oriented_box_margin


class PlanningEvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trajectory_collision_count: int = 0
    min_trajectory_margin: float | None = None
    min_margin_time: float | None = None
    collision_start_time: float | None = None
    diagnosable_frames: int = 0
    evidence: list[EvidenceRecord] = Field(default_factory=list)


DIAGNOSABLE_SOURCES = {
    TrajectorySource.OFFLINE_PLANNER,
    TrajectorySource.PERTURBED_PLANNER,
    TrajectorySource.MODEL_PREDICTION,
}


def evaluate_planning(
    scenario: ScenarioRecord,
    factory: EvidenceFactory | None = None,
    collision_margin: float = 0.5,
) -> PlanningEvalResult:
    factory = factory or EvidenceFactory()
    collision_count = 0
    min_margin: float | None = None
    min_margin_time: float | None = None
    collision_start_time: float | None = None
    diagnosable_frames = 0

    for frame in scenario.frames:
        if not frame.planning.available or frame.planning.trajectory_source not in DIAGNOSABLE_SOURCES:
            continue
        diagnosable_frames += 1
        for point in frame.planning.trajectory:
            if point.dt <= 0:
                continue
            for actor in frame.actors_gt:
                actor_x = actor.x + actor.vx * point.dt
                actor_y = actor.y + actor.vy * point.dt
                margin = oriented_box_margin(
                    point.x,
                    point.y,
                    point.yaw if point.yaw is not None else frame.ego.yaw,
                    actor_x,
                    actor_y,
                    actor.yaw,
                    actor.length,
                    actor.width,
                    frame.ego.length,
                    frame.ego.width,
                )
                if min_margin is None or margin < min_margin:
                    min_margin = margin
                    min_margin_time = frame.timestamp
                if margin <= collision_margin:
                    collision_count += 1
                    if collision_start_time is None:
                        collision_start_time = frame.timestamp

    evidence: list[EvidenceRecord] = []
    if collision_count:
        evidence.append(
            factory.make(
                "PLAN",
                "trajectory_collision_count",
                collision_count,
                0.0,
                collision_start_time,
                "violation",
                supports=["planning_collision_risk"],
                contradicts=["normal"],
                description="Diagnosable planning trajectory intersects or approaches actor footprint.",
            )
        )
    elif diagnosable_frames:
        evidence.append(
            factory.make(
                "PLAN",
                "trajectory_collision_count",
                0,
                collision_margin,
                min_margin_time,
                "normal",
                supports=["normal"],
                contradicts=["planning_collision_risk"],
                description="Diagnosable planning trajectory remains clear of actor footprints.",
            )
        )

    return PlanningEvalResult(
        trajectory_collision_count=collision_count,
        min_trajectory_margin=min_margin,
        min_margin_time=min_margin_time,
        collision_start_time=collision_start_time,
        diagnosable_frames=diagnosable_frames,
        evidence=evidence,
    )
