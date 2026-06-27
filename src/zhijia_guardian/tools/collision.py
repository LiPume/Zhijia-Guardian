from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.evidence import EvidenceFactory
from zhijia_guardian.utils.geometry import oriented_box_margin


class CollisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collision_count: int = 0
    min_margin: float | None = None
    min_margin_time: float | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)


def detect_collisions(
    scenario: ScenarioRecord,
    factory: EvidenceFactory | None = None,
    collision_margin: float = 0.0,
) -> CollisionResult:
    factory = factory or EvidenceFactory()
    collision_count = 0
    min_margin: float | None = None
    min_margin_time: float | None = None

    for frame in scenario.frames:
        for actor in frame.actors_gt:
            margin = oriented_box_margin(
                frame.ego.x,
                frame.ego.y,
                frame.ego.yaw,
                actor.x,
                actor.y,
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

    evidence: list[EvidenceRecord] = []
    if collision_count:
        evidence.append(
            factory.make(
                "COLL",
                "collision_count",
                collision_count,
                collision_margin,
                min_margin_time,
                "violation",
                supports=["planning_collision_risk", "control_delay"],
                contradicts=["normal"],
                description="Ego overlaps or gets too close to actor footprint.",
            )
        )
    elif min_margin is not None:
        evidence.append(
            factory.make(
                "COLL",
                "collision_count",
                0,
                collision_margin,
                min_margin_time,
                "normal",
                supports=["normal"],
                contradicts=["planning_collision_risk"],
                description="No actor footprint overlap detected.",
            )
        )

    return CollisionResult(
        collision_count=collision_count,
        min_margin=min_margin,
        min_margin_time=min_margin_time,
        evidence=evidence,
    )
