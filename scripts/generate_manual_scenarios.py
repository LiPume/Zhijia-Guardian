#!/usr/bin/env python
from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.benchmarks.manual_v0_3 import build_manual_v0_3_records  # noqa: E402
from zhijia_guardian.schemas.scenario import (  # noqa: E402
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
from zhijia_guardian.utils.io import dump_scenario_record  # noqa: E402


FAULT_TYPES = [
    "normal",
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "planning_collision_risk",
    "control_delay",
]

SUBSET_BY_FAULT = {
    "normal": ["planning_like_nuplan", "full_stack_like_carla"],
    "perception_miss": ["perception_like_nuscenes", "full_stack_like_carla"],
    "perception_false_positive": ["perception_like_nuscenes", "full_stack_like_carla"],
    "perception_confidence_drop": ["perception_like_nuscenes", "full_stack_like_carla"],
    "planning_collision_risk": ["planning_like_nuplan", "full_stack_like_carla"],
    "control_delay": ["full_stack_like_carla"],
}

ROOT_BY_FAULT = {
    "normal": "none",
    "perception_miss": "perception",
    "perception_false_positive": "perception",
    "perception_confidence_drop": "perception",
    "planning_collision_risk": "planning",
    "control_delay": "control",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate noisy manual canonical scenarios.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=72)
    parser.add_argument("--version", choices=("v0_1", "v0_3"), default="v0_1")
    parser.add_argument("--output", default=None)
    parser.add_argument("--clean", action="store_true", help="Remove output directory before writing.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.count < 6:
        raise ValueError("--count must be at least 6")
    output = Path(args.output or f"data/sample_scenarios/manual_json/{args.version}")
    if args.clean and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    if args.version == "v0_3":
        records = build_manual_v0_3_records(count=args.count, seed=args.seed)
    else:
        rng = random.Random(args.seed)
        records = []
        faults = balanced_faults(args.count)
        rng.shuffle(faults)
        for index, fault_type in enumerate(faults, start=1):
            subset = rng.choice(SUBSET_BY_FAULT[fault_type])
            difficulty = choose_difficulty(rng, fault_type)
            scenario_id = f"manual_v0_1_{index:06d}"
            records.append(generate_record(scenario_id, fault_type, subset, difficulty, args.seed, rng))

    for record in records:
        subset = record.source.raw_log_id or "unknown"
        dump_scenario_record(record, output / subset / f"{record.scenario_id}.json")

    print(f"Generated {len(records)} noisy manual scenarios under {output}")
    print("Distribution:")
    for fault in FAULT_TYPES:
        print(f"- {fault}: {sum(r.oracle and r.oracle.fault_type == fault for r in records)}")


def balanced_faults(count: int) -> list[str]:
    faults: list[str] = []
    while len(faults) < count:
        faults.extend(FAULT_TYPES)
    return faults[:count]


def choose_difficulty(rng: random.Random, fault_type: str) -> str:
    if fault_type == "normal":
        return rng.choice(["easy", "boundary"])
    return rng.choice(["easy", "moderate", "boundary", "composite"])


def generate_record(
    scenario_id: str,
    fault_type: str,
    subset: str,
    difficulty: str,
    seed: int,
    rng: random.Random,
) -> ScenarioRecord:
    fault_nominal_time = 2.5
    fault_time = round(fault_nominal_time + rng.uniform(-0.2, 0.2), 2) if fault_type != "normal" else None
    frames = build_frames(fault_type, subset, difficulty, fault_time, rng)
    events = observed_events(fault_type, fault_time, difficulty)
    return ScenarioRecord(
        scenario_id=scenario_id,
        source=SourceInfo(
            dataset="manual_json",
            version="v0_1",
            raw_log_id=subset,
            raw_tokens={},
            generation={
                "generation_seed": seed,
                "noise_profile": "v0_1_moderate",
                "scenario_family": scenario_family(fault_type, difficulty),
                "difficulty": difficulty,
            },
        ),
        meta=MetaInfo(frequency_hz=2.0, duration=frames[-1].timestamp - frames[0].timestamp),
        frames=frames,
        events_observed=events,
        oracle=OracleRecord(
            fault_type=fault_type,
            root_module=ROOT_BY_FAULT[fault_type],
            fault_start_time=fault_time,
            fault_segment=(fault_time, min(fault_time + 1.5, frames[-1].timestamp)) if fault_time is not None else None,
        ),
    )


def build_frames(
    fault_type: str,
    subset: str,
    difficulty: str,
    fault_time: float | None,
    rng: random.Random,
) -> list[FrameRecord]:
    frames: list[FrameRecord] = []
    ego_speed = rng.uniform(5.5, 9.0)
    actor_x0 = rng.uniform(22.0, 35.0)
    actor_vx = rng.choice([0.0, rng.uniform(1.0, 4.0)])
    if difficulty == "boundary":
        actor_x0 = rng.uniform(30.0, 42.0)
        actor_vx = rng.uniform(2.5, 6.0)
    if fault_type == "control_delay":
        actor_x0 = rng.uniform(22.0, 28.0)
        actor_vx = 0.0
        ego_speed = rng.uniform(7.5, 9.5)
    if fault_type == "planning_collision_risk":
        actor_x0 = rng.uniform(20.0, 28.0)
        actor_vx = rng.uniform(0.0, 2.0)
        ego_speed = rng.uniform(4.5, 7.0)

    for i in range(11):
        timestamp = round(i * 0.5, 2)
        ego = noisy_ego(timestamp, ego_speed, rng)
        actors = actors_for_frame(timestamp, actor_x0, actor_vx, rng, include_actor=fault_type != "perception_false_positive")
        perception = perception_for_frame(fault_type, subset, difficulty, timestamp, fault_time, actors, rng)
        planning = planning_for_frame(fault_type, subset, difficulty, timestamp, ego, actors, rng)
        control = control_for_frame(fault_type, subset, timestamp, fault_time, rng)
        frames.append(
            FrameRecord(
                timestamp=timestamp,
                ego=ego,
                actors_gt=actors,
                actors_gt_source=ActorGtSource.SIMULATION if actors else ActorGtSource.UNAVAILABLE,
                perception=perception,
                planning=planning,
                control=control,
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return frames


def noisy_ego(timestamp: float, speed: float, rng: random.Random) -> EgoState:
    return EgoState(
        x=speed * timestamp + rng.gauss(0.0, 0.08),
        y=rng.gauss(0.0, 0.04),
        vx=speed + rng.gauss(0.0, 0.12),
        vy=rng.gauss(0.0, 0.03),
        ax=rng.gauss(0.0, 0.08),
    )


def actors_for_frame(timestamp: float, x0: float, vx: float, rng: random.Random, include_actor: bool) -> list[ActorState]:
    if not include_actor:
        return []
    return [
        ActorState(
            actor_id="veh_001",
            type="vehicle",
            x=x0 + vx * timestamp + rng.gauss(0.0, 0.12),
            y=rng.gauss(0.0, 0.06),
            vx=vx + rng.gauss(0.0, 0.08),
            vy=rng.gauss(0.0, 0.03),
            length=4.5,
            width=1.9,
            is_key_actor=True,
        )
    ]


def perception_for_frame(
    fault_type: str,
    subset: str,
    difficulty: str,
    timestamp: float,
    fault_time: float | None,
    actors: list[ActorState],
    rng: random.Random,
) -> PerceptionState:
    if subset == "planning_like_nuplan":
        return PerceptionState(available=False)
    detections: list[Detection] = []
    for actor in actors:
        if fault_type == "perception_miss" and fault_time is not None and timestamp >= fault_time:
            if rng.random() < 0.75:
                continue
        base_conf = 0.78 + rng.gauss(0.0, 0.06)
        if fault_type == "perception_confidence_drop" and fault_time is not None and timestamp >= fault_time:
            base_conf = 0.22 + rng.gauss(0.0, 0.05)
        if difficulty == "composite" and fault_type == "planning_collision_risk" and rng.random() < 0.15:
            base_conf = 0.3
        detections.append(
            Detection(
                track_id=f"det_{actor.actor_id}",
                type=actor.type,
                confidence=max(0.0, min(1.0, base_conf)),
                x=actor.x + rng.gauss(0.0, 0.35),
                y=actor.y + rng.gauss(0.0, 0.18),
                length=actor.length + rng.gauss(0.0, 0.05),
                width=actor.width + rng.gauss(0.0, 0.04),
                matched_gt_id=actor.actor_id,
            )
        )
    if fault_type == "perception_false_positive" and fault_time is not None and timestamp >= fault_time:
        detections.append(
            Detection(
                track_id="ghost_001",
                type="vehicle",
                confidence=max(0.35, min(0.95, 0.74 + rng.gauss(0.0, 0.08))),
                x=(timestamp * 7.0) + rng.uniform(9.0, 17.0),
                y=rng.gauss(0.0, 0.3),
                length=4.5,
                width=1.9,
            )
        )
    return PerceptionState(
        available=True,
        detection_source=DetectionSource.SYNTHETIC_FROM_ANNOTATION,
        detections=detections,
    )


def planning_for_frame(
    fault_type: str,
    subset: str,
    difficulty: str,
    timestamp: float,
    ego: EgoState,
    actors: list[ActorState],
    rng: random.Random,
) -> PlanningState:
    if subset == "perception_like_nuscenes":
        return PlanningState(available=False)
    source = TrajectorySource.OFFLINE_PLANNER
    y_offset = 3.8
    step = 2.3
    if fault_type == "planning_collision_risk":
        source = TrajectorySource.PERTURBED_PLANNER
        y_offset = 0.0
        step = 2.8
    elif fault_type == "control_delay":
        source = TrajectorySource.MODEL_PREDICTION
        y_offset = 3.6
        step = 0.8
    if fault_type == "normal" and difficulty == "boundary":
        y_offset = rng.choice([2.8, 3.2])
    trajectory = [
        TrajectoryPoint(
            dt=j * 0.5,
            x=ego.x + j * step + rng.gauss(0.0, 0.05),
            y=y_offset + rng.gauss(0.0, 0.05),
            speed=max(0.0, ego.vx - j * 0.2),
        )
        for j in range(6)
    ]
    return PlanningState(
        available=True,
        trajectory_source=source,
        trajectory=trajectory,
        intent="keep_lane" if y_offset == 0.0 else "safe_offset",
        target_speed=max(0.0, ego.vx),
    )


def control_for_frame(
    fault_type: str,
    subset: str,
    timestamp: float,
    fault_time: float | None,
    rng: random.Random,
) -> ControlState:
    if subset != "full_stack_like_carla":
        return ControlState(available=False)
    brake = max(0.0, rng.gauss(0.02, 0.015))
    throttle = max(0.0, min(1.0, rng.gauss(0.25, 0.04)))
    if fault_type == "control_delay" and fault_time is not None:
        brake_start = fault_time + rng.uniform(1.0, 1.8)
        if timestamp >= brake_start:
            brake = max(0.3, min(1.0, rng.gauss(0.45, 0.08)))
            throttle = max(0.0, rng.gauss(0.05, 0.03))
    elif fault_type == "normal":
        if fault_time is not None and timestamp >= fault_time:
            brake = max(0.25, min(1.0, rng.gauss(0.35, 0.06)))
    return ControlState(available=True, steer=rng.gauss(0.0, 0.02), throttle=throttle, brake=brake)


def observed_events(fault_type: str, fault_time: float | None, difficulty: str) -> list[EventRecord]:
    if fault_time is None:
        return [
            EventRecord(
                event_type="boundary_driving_context",
                timestamp=0.0,
                description="Traffic context is close to a risk threshold but has no injected fault metadata.",
                attributes={"difficulty": difficulty},
            )
        ]
    return [
        EventRecord(
            event_type="risk_context",
            timestamp=fault_time,
            description="observed anomaly or safety-relevant context",
            attributes={"difficulty": difficulty},
        )
    ]


def scenario_family(fault_type: str, difficulty: str) -> str:
    if fault_type == "perception_false_positive":
        return "ghost_obstacle"
    if fault_type in {"perception_miss", "perception_confidence_drop", "control_delay"}:
        return "front_vehicle_interaction"
    if fault_type == "planning_collision_risk":
        return "static_or_slow_obstacle"
    return f"normal_{difficulty}"


if __name__ == "__main__":
    main()
