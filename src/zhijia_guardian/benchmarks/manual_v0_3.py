from __future__ import annotations

import math
import random

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
    TrajectoryPoint,
    TrajectorySource,
)


FAULT_TYPES = (
    "normal",
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "planning_collision_risk",
    "control_delay",
)

SUBSET_BY_FAULT = {
    "normal": ("planning_like_nuplan", "full_stack_like_carla"),
    "perception_miss": ("perception_like_nuscenes", "full_stack_like_carla"),
    "perception_false_positive": ("perception_like_nuscenes", "full_stack_like_carla"),
    "perception_confidence_drop": ("perception_like_nuscenes", "full_stack_like_carla"),
    "planning_collision_risk": ("planning_like_nuplan", "full_stack_like_carla"),
    "control_delay": ("full_stack_like_carla",),
}

ROOT_BY_FAULT = {
    "normal": "none",
    "perception_miss": "perception",
    "perception_false_positive": "perception",
    "perception_confidence_drop": "perception",
    "planning_collision_risk": "planning",
    "control_delay": "control",
}


def build_manual_v0_3_records(count: int = 72, seed: int = 42) -> list[ScenarioRecord]:
    """Build canonical manual records whose oracle follows observable event timing."""
    if count < len(FAULT_TYPES):
        raise ValueError(f"count must be at least {len(FAULT_TYPES)}")

    rng = random.Random(seed)
    faults = _balanced_faults(count)
    rng.shuffle(faults)
    records = []
    for index, fault_type in enumerate(faults, start=1):
        difficulty = _choose_difficulty(rng, fault_type)
        if difficulty == "composite" and "full_stack_like_carla" in SUBSET_BY_FAULT[fault_type]:
            subset = "full_stack_like_carla"
        else:
            subset = rng.choice(SUBSET_BY_FAULT[fault_type])
        records.append(
            _build_record(
                scenario_id=f"manual_v0_3_{index:06d}",
                fault_type=fault_type,
                subset=subset,
                difficulty=difficulty,
                seed=seed,
                rng=rng,
            )
        )
    return records


def _balanced_faults(count: int) -> list[str]:
    return [FAULT_TYPES[index % len(FAULT_TYPES)] for index in range(count)]


def _choose_difficulty(rng: random.Random, fault_type: str) -> str:
    if fault_type == "normal":
        return rng.choice(("easy", "boundary"))
    return rng.choice(("easy", "moderate", "boundary", "composite"))


def _build_record(
    scenario_id: str,
    fault_type: str,
    subset: str,
    difficulty: str,
    seed: int,
    rng: random.Random,
) -> ScenarioRecord:
    kinematics = _build_kinematics(fault_type, difficulty, rng)
    risk_time = _first_ttc_risk_time(kinematics)
    fault_time = _resolve_fault_time(fault_type, risk_time, rng)
    frames = _build_frames(
        kinematics=kinematics,
        fault_type=fault_type,
        subset=subset,
        difficulty=difficulty,
        fault_time=fault_time,
        risk_time=risk_time,
        rng=rng,
    )
    return ScenarioRecord(
        scenario_id=scenario_id,
        source=SourceInfo(
            dataset="manual_json",
            version="v0_3",
            raw_log_id=subset,
            raw_tokens={},
            generation={
                "benchmark": "manual_canonical_v0_3",
                "generation_seed": seed,
                "noise_profile": "v0_3_temporal_consistent",
                "scenario_family": _scenario_family(fault_type, difficulty),
                "difficulty": difficulty,
                "timing_policy": "first_ttc_crossing",
            },
        ),
        meta=MetaInfo(frequency_hz=2.0, duration=frames[-1].timestamp),
        frames=frames,
        events_observed=_observed_events(risk_time, difficulty),
        oracle=OracleRecord(
            fault_type=fault_type,
            root_module=ROOT_BY_FAULT[fault_type],
            fault_start_time=fault_time,
            fault_segment=(fault_time, min(fault_time + 1.5, frames[-1].timestamp))
            if fault_time is not None
            else None,
        ),
    )


def _build_kinematics(
    fault_type: str,
    difficulty: str,
    rng: random.Random,
) -> list[tuple[float, EgoState, list[ActorState]]]:
    if fault_type == "normal":
        ego_speed = rng.uniform(5.5, 7.5)
        actor_x0 = rng.uniform(36.0, 44.0)
        actor_vx = rng.uniform(4.5, 7.0)
        if difficulty == "boundary":
            actor_x0 = rng.uniform(25.0, 31.0)
            actor_vx = max(ego_speed - rng.uniform(2.0, 3.5), 0.5)
    elif fault_type == "perception_false_positive":
        ego_speed = rng.uniform(5.5, 8.5)
        actor_x0 = 0.0
        actor_vx = 0.0
    elif fault_type == "planning_collision_risk":
        ego_speed = rng.uniform(5.5, 7.5)
        actor_x0 = rng.uniform(22.0, 28.0)
        actor_vx = rng.uniform(0.0, 1.5)
    else:
        ego_speed = rng.uniform(7.0, 9.5)
        actor_x0 = rng.uniform(23.0, 30.0)
        actor_vx = rng.uniform(0.0, 2.0)

    if difficulty == "boundary" and fault_type not in {"normal", "perception_false_positive"}:
        actor_x0 += rng.uniform(2.0, 4.0)
        actor_vx += rng.uniform(0.5, 1.5)

    frames = []
    for index in range(11):
        timestamp = index * 0.5
        ego = EgoState(
            x=ego_speed * timestamp + rng.gauss(0.0, 0.06),
            y=rng.gauss(0.0, 0.03),
            vx=ego_speed + rng.gauss(0.0, 0.08),
            vy=rng.gauss(0.0, 0.02),
            ax=rng.gauss(0.0, 0.06),
        )
        actors = []
        if fault_type != "perception_false_positive":
            actors.append(
                ActorState(
                    actor_id="veh_001",
                    type="vehicle",
                    x=actor_x0 + actor_vx * timestamp + rng.gauss(0.0, 0.08),
                    y=rng.gauss(0.0, 0.04),
                    vx=actor_vx + rng.gauss(0.0, 0.05),
                    vy=rng.gauss(0.0, 0.02),
                    length=4.5,
                    width=1.9,
                    is_key_actor=True,
                )
            )
        frames.append((timestamp, ego, actors))
    return frames


def _first_ttc_risk_time(
    kinematics: list[tuple[float, EgoState, list[ActorState]]],
    threshold: float = 1.5,
) -> float | None:
    for timestamp, ego, actors in kinematics:
        heading_x = math.cos(ego.yaw)
        heading_y = math.sin(ego.yaw)
        for actor in actors:
            dx = actor.x - ego.x
            dy = actor.y - ego.y
            longitudinal = dx * heading_x + dy * heading_y
            lateral = -dx * heading_y + dy * heading_x
            closing_speed = (ego.vx - actor.vx) * heading_x + (ego.vy - actor.vy) * heading_y
            if abs(lateral) <= 3.0 and longitudinal > 0.0 and closing_speed > 0.1:
                if longitudinal / closing_speed < threshold:
                    return timestamp
    return None


def _resolve_fault_time(
    fault_type: str,
    risk_time: float | None,
    rng: random.Random,
) -> float | None:
    if fault_type == "normal":
        return None
    if fault_type == "perception_false_positive":
        return rng.choice((1.5, 2.0, 2.5))
    if risk_time is None:
        raise RuntimeError(f"{fault_type} scenario did not reach the TTC risk threshold")
    if fault_type == "control_delay":
        return risk_time
    lead_time = rng.choice((0.5, 1.0))
    return max(0.5, risk_time - lead_time)


def _build_frames(
    kinematics: list[tuple[float, EgoState, list[ActorState]]],
    fault_type: str,
    subset: str,
    difficulty: str,
    fault_time: float | None,
    risk_time: float | None,
    rng: random.Random,
) -> list[FrameRecord]:
    frames = []
    for timestamp, ego, actors in kinematics:
        frames.append(
            FrameRecord(
                timestamp=timestamp,
                ego=ego,
                actors_gt=actors,
                actors_gt_source=ActorGtSource.SIMULATION if actors else ActorGtSource.UNAVAILABLE,
                perception=_perception_state(fault_type, subset, timestamp, fault_time, actors, rng),
                planning=_planning_state(fault_type, subset, timestamp, fault_time, ego, actors, rng),
                control=_control_state(
                    fault_type,
                    subset,
                    difficulty,
                    timestamp,
                    risk_time,
                    rng,
                ),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return frames


def _perception_state(
    fault_type: str,
    subset: str,
    timestamp: float,
    fault_time: float | None,
    actors: list[ActorState],
    rng: random.Random,
) -> PerceptionState:
    if subset == "planning_like_nuplan":
        return PerceptionState(available=False)

    detections = []
    active = fault_time is not None and timestamp >= fault_time
    for actor in actors:
        if fault_type == "perception_miss" and active:
            continue
        confidence = max(0.55, min(0.95, 0.8 + rng.gauss(0.0, 0.04)))
        if fault_type == "perception_confidence_drop" and active:
            confidence = max(0.36, min(0.42, 0.39 + rng.gauss(0.0, 0.01)))
        detections.append(
            Detection(
                track_id=f"det_{actor.actor_id}",
                type=actor.type,
                confidence=confidence,
                x=actor.x + rng.gauss(0.0, 0.3),
                y=actor.y + rng.gauss(0.0, 0.15),
                length=actor.length + rng.gauss(0.0, 0.04),
                width=actor.width + rng.gauss(0.0, 0.03),
                matched_gt_id=actor.actor_id,
            )
        )
    if fault_type == "perception_false_positive" and active:
        detections.append(
            Detection(
                track_id="ghost_001",
                type="vehicle",
                confidence=max(0.55, min(0.9, 0.74 + rng.gauss(0.0, 0.05))),
                x=timestamp * 7.0 + rng.uniform(10.0, 15.0),
                y=rng.gauss(0.0, 0.2),
                length=4.5,
                width=1.9,
            )
        )
    return PerceptionState(
        available=True,
        detection_source=DetectionSource.SYNTHETIC_FROM_ANNOTATION,
        detections=detections,
    )


def _planning_state(
    fault_type: str,
    subset: str,
    timestamp: float,
    fault_time: float | None,
    ego: EgoState,
    actors: list[ActorState],
    rng: random.Random,
) -> PlanningState:
    if subset == "perception_like_nuscenes":
        return PlanningState(available=False)

    active = fault_type == "planning_collision_risk" and fault_time is not None and timestamp >= fault_time
    source = TrajectorySource.PERTURBED_PLANNER if active else TrajectorySource.OFFLINE_PLANNER
    trajectory = _safe_trajectory(ego, rng)
    if active and actors:
        trajectory = _collision_trajectory(ego, actors[0], rng)
    return PlanningState(
        available=True,
        trajectory_source=source,
        trajectory=trajectory,
        intent="unsafe_keep_lane" if active else "safe_offset",
        target_speed=max(0.0, ego.vx),
    )


def _safe_trajectory(ego: EgoState, rng: random.Random) -> list[TrajectoryPoint]:
    return [
        TrajectoryPoint(
            dt=index * 0.5,
            x=ego.x + index * 2.0 + rng.gauss(0.0, 0.03),
            y=3.8 + rng.gauss(0.0, 0.03),
            speed=max(0.0, ego.vx - index * 0.2),
        )
        for index in range(6)
    ]


def _collision_trajectory(
    ego: EgoState,
    actor: ActorState,
    rng: random.Random,
) -> list[TrajectoryPoint]:
    target_index = 3
    target_dt = target_index * 0.5
    target_x = actor.x + actor.vx * target_dt
    target_y = actor.y + actor.vy * target_dt
    step_x = (target_x - ego.x) / target_index
    step_y = (target_y - ego.y) / target_index
    return [
        TrajectoryPoint(
            dt=index * 0.5,
            x=ego.x + index * step_x + (rng.gauss(0.0, 0.01) if index != target_index else 0.0),
            y=ego.y + index * step_y + (rng.gauss(0.0, 0.01) if index != target_index else 0.0),
            speed=max(0.0, ego.vx - index * 0.1),
        )
        for index in range(6)
    ]


def _control_state(
    fault_type: str,
    subset: str,
    difficulty: str,
    timestamp: float,
    risk_time: float | None,
    rng: random.Random,
) -> ControlState:
    if subset != "full_stack_like_carla":
        return ControlState(available=False)

    brake_start = risk_time
    if risk_time is not None and (
        fault_type == "control_delay"
        or (difficulty == "composite" and fault_type.startswith("perception_"))
        or (difficulty == "composite" and fault_type == "planning_collision_risk")
    ):
        brake_start = risk_time + 1.0

    braking = brake_start is not None and timestamp >= brake_start
    if braking:
        brake = max(0.3, min(0.7, rng.gauss(0.45, 0.05)))
        throttle = max(0.0, min(0.1, rng.gauss(0.04, 0.02)))
    else:
        brake = max(0.0, min(0.08, rng.gauss(0.02, 0.01)))
        throttle = max(0.12, min(0.4, rng.gauss(0.25, 0.03)))
    return ControlState(
        available=True,
        steer=rng.gauss(0.0, 0.015),
        throttle=throttle,
        brake=brake,
    )


def _observed_events(risk_time: float | None, difficulty: str) -> list[EventRecord]:
    events = [
        EventRecord(
            event_type="traffic_context",
            timestamp=0.0,
            description="Canonical synthetic driving sequence.",
            attributes={"difficulty": difficulty},
        )
    ]
    if risk_time is not None:
        events.append(
            EventRecord(
                event_type="proximity_warning",
                timestamp=risk_time,
                description="Observed longitudinal proximity entered the configured risk range.",
            )
        )
    return events


def _scenario_family(fault_type: str, difficulty: str) -> str:
    if fault_type == "perception_false_positive":
        return "ghost_obstacle"
    if fault_type in {"perception_miss", "perception_confidence_drop", "control_delay"}:
        return "front_vehicle_interaction"
    if fault_type == "planning_collision_risk":
        return "static_or_slow_obstacle"
    return f"normal_{difficulty}"
