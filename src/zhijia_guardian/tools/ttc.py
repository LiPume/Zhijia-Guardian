from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.evidence import EvidenceFactory
from zhijia_guardian.utils.geometry import euclidean_distance


class TtcPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: float
    actor_id: str
    distance: float
    ttc: float | None


class TtcResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: list[TtcPoint] = Field(default_factory=list)
    min_ttc: float | None = None
    min_ttc_time: float | None = None
    min_distance: float | None = None
    min_distance_time: float | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)


def compute_ttc(
    scenario: ScenarioRecord,
    factory: EvidenceFactory | None = None,
    ttc_threshold: float = 1.5,
    max_lateral_offset: float = 3.0,
) -> TtcResult:
    factory = factory or EvidenceFactory()
    points: list[TtcPoint] = []
    min_ttc: float | None = None
    min_ttc_time: float | None = None
    min_distance: float | None = None
    min_distance_time: float | None = None

    for frame in scenario.frames:
        ego = frame.ego
        for actor in frame.actors_gt:
            dx = actor.x - ego.x
            dy = actor.y - ego.y
            distance = euclidean_distance(ego.x, ego.y, actor.x, actor.y)
            if min_distance is None or distance < min_distance:
                min_distance = distance
                min_distance_time = frame.timestamp

            # Lightweight lane-aligned TTC for canonical demos and smoke tests.
            if abs(dy) > max_lateral_offset or dx <= 0:
                ttc = None
            else:
                closing_speed = ego.vx - actor.vx
                ttc = dx / closing_speed if closing_speed > 0.1 else None
            points.append(TtcPoint(timestamp=frame.timestamp, actor_id=actor.actor_id, distance=distance, ttc=ttc))
            if ttc is not None and math.isfinite(ttc):
                if min_ttc is None or ttc < min_ttc:
                    min_ttc = ttc
                    min_ttc_time = frame.timestamp

    evidence: list[EvidenceRecord] = []
    if min_ttc is not None and min_ttc < ttc_threshold:
        evidence.append(
            factory.make(
                "TTC",
                "min_ttc",
                round(min_ttc, 3),
                ttc_threshold,
                min_ttc_time,
                "violation",
                supports=["planning_collision_risk", "control_delay"],
                contradicts=["normal"],
                description="Minimum TTC is below safety threshold.",
            )
        )
    elif min_ttc is not None:
        evidence.append(
            factory.make(
                "TTC",
                "min_ttc",
                round(min_ttc, 3),
                ttc_threshold,
                min_ttc_time,
                "normal",
                supports=["normal"],
                contradicts=["planning_collision_risk", "control_delay"],
                description="Minimum TTC stays above safety threshold.",
            )
        )

    if min_distance is not None:
        evidence.append(
            factory.make(
                "DIST",
                "min_distance",
                round(min_distance, 3),
                None,
                min_distance_time,
                "uncertain",
                description="Minimum ego-to-actor center distance.",
            )
        )

    return TtcResult(
        points=points,
        min_ttc=min_ttc,
        min_ttc_time=min_ttc_time,
        min_distance=min_distance,
        min_distance_time=min_distance_time,
        evidence=evidence,
    )
