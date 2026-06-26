from __future__ import annotations

from collections import Counter
from typing import Any

from zhijia_guardian.schemas.scenario import ScenarioRecord, TrajectorySource


def field_coverage(record: ScenarioRecord) -> dict[str, Any]:
    n_frames = len(record.frames)
    perception_available = sum(frame.perception.available for frame in record.frames)
    planning_available = sum(frame.planning.available for frame in record.frames)
    control_available = sum(frame.control.available for frame in record.frames)
    map_available = sum(frame.map.available for frame in record.frames)
    actor_sources = Counter(frame.actors_gt_source.value for frame in record.frames)
    trajectory_sources = Counter(frame.planning.trajectory_source.value for frame in record.frames)
    detection_sources = Counter(frame.perception.detection_source.value for frame in record.frames)
    diagnosable_planning_frames = sum(
        frame.planning.trajectory_source in {
            TrajectorySource.OFFLINE_PLANNER,
            TrajectorySource.PERTURBED_PLANNER,
            TrajectorySource.MODEL_PREDICTION,
        }
        for frame in record.frames
    )
    skipped_agents: list[str] = []
    if perception_available == 0:
        skipped_agents.append("perception_agent")
    if diagnosable_planning_frames == 0:
        skipped_agents.append("planning_fault_agent")
    if control_available == 0:
        skipped_agents.append("control_agent")

    return {
        "scenario_id": record.scenario_id,
        "dataset": record.source.dataset,
        "num_frames": n_frames,
        "duration": record.meta.duration,
        "perception_available_frames": perception_available,
        "planning_available_frames": planning_available,
        "diagnosable_planning_frames": diagnosable_planning_frames,
        "control_available_frames": control_available,
        "map_available_frames": map_available,
        "actor_gt_sources": dict(actor_sources),
        "trajectory_sources": dict(trajectory_sources),
        "detection_sources": dict(detection_sources),
        "events_observed": len(record.events_observed),
        "skipped_agents": skipped_agents,
        "has_oracle": record.oracle is not None,
    }
