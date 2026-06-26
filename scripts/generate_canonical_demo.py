#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.schemas.scenario import (  # noqa: E402
    ActorGtSource,
    ActorState,
    ControlState,
    Detection,
    DetectionSource,
    EgoState,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate six canonical demo scenarios.")
    parser.add_argument("--output-dir", default="data/sample_scenarios/canonical_demo")
    return parser.parse_args()


def ego_at(t: float, speed: float = 8.0) -> EgoState:
    return EgoState(x=speed * t, y=0.0, vx=speed, vy=0.0, ax=0.0)


def front_actor(t: float, actor_id: str = "veh_001", x0: float = 28.0, vx: float = 0.0) -> ActorState:
    return ActorState(
        actor_id=actor_id,
        type="vehicle",
        x=x0 + vx * t,
        y=0.0,
        vx=vx,
        vy=0.0,
        length=4.5,
        width=1.9,
        is_key_actor=True,
    )


def detection_for_actor(actor: ActorState, confidence: float, track_id: str = "det_001") -> Detection:
    return Detection(
        track_id=track_id,
        type=actor.type,
        confidence=confidence,
        x=actor.x + 0.15,
        y=actor.y - 0.1,
        length=actor.length,
        width=actor.width,
        matched_gt_id=actor.actor_id,
    )


def base_record(scenario_id: str, subset: str, frames: list[FrameRecord], oracle: OracleRecord) -> ScenarioRecord:
    return ScenarioRecord(
        scenario_id=scenario_id,
        source=SourceInfo(
            dataset="manual_json",
            version="v0_1",
            raw_log_id=subset,
            raw_tokens={},
        ),
        meta=MetaInfo(frequency_hz=2.0, duration=frames[-1].timestamp - frames[0].timestamp),
        frames=frames,
        events_observed=[],
        oracle=oracle,
    )


def perception_miss_demo(scenario_id: str) -> ScenarioRecord:
    frames: list[FrameRecord] = []
    for i in range(11):
        t = i * 0.5
        actor = front_actor(t, x0=24.0, vx=0.0)
        detections = [] if t >= 2.0 else [detection_for_actor(actor, 0.82)]
        frames.append(
            FrameRecord(
                timestamp=t,
                ego=ego_at(t, 7.5),
                actors_gt=[actor],
                actors_gt_source=ActorGtSource.SIMULATION,
                perception=PerceptionState(
                    available=True,
                    detection_source=DetectionSource.SYNTHETIC_FROM_ANNOTATION,
                    detections=detections,
                ),
                planning=PlanningState(available=False),
                control=ControlState(available=False),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return base_record(
        scenario_id,
        "perception_like_nuscenes",
        frames,
        OracleRecord(fault_type="perception_miss", root_module="perception", fault_start_time=2.0),
    )


def false_positive_demo(scenario_id: str) -> ScenarioRecord:
    frames: list[FrameRecord] = []
    for i in range(11):
        t = i * 0.5
        detections = []
        if t >= 2.0:
            detections.append(
                Detection(track_id="ghost_001", type="vehicle", confidence=0.78, x=ego_at(t).x + 12.0, y=0.0, length=4.5, width=1.9)
            )
        frames.append(
            FrameRecord(
                timestamp=t,
                ego=ego_at(t, 8.0),
                actors_gt=[],
                actors_gt_source=ActorGtSource.UNAVAILABLE,
                perception=PerceptionState(
                    available=True,
                    detection_source=DetectionSource.SYNTHETIC_FROM_ANNOTATION,
                    detections=detections,
                ),
                planning=PlanningState(available=False),
                control=ControlState(available=False),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return base_record(
        scenario_id,
        "perception_like_nuscenes",
        frames,
        OracleRecord(fault_type="perception_false_positive", root_module="perception", fault_start_time=2.0),
    )


def planning_collision_demo(scenario_id: str) -> ScenarioRecord:
    frames: list[FrameRecord] = []
    for i in range(11):
        t = i * 0.5
        ego = ego_at(t, 5.0)
        actor = front_actor(t, x0=22.0, vx=0.0)
        trajectory = [TrajectoryPoint(dt=j * 0.5, x=ego.x + j * 3.0, y=0.0, speed=6.0) for j in range(6)]
        frames.append(
            FrameRecord(
                timestamp=t,
                ego=ego,
                actors_gt=[actor],
                actors_gt_source=ActorGtSource.SIMULATION,
                perception=PerceptionState(available=False),
                planning=PlanningState(
                    available=True,
                    trajectory_source=TrajectorySource.PERTURBED_PLANNER,
                    trajectory=trajectory,
                    intent="keep_lane",
                    target_speed=6.0,
                ),
                control=ControlState(available=False),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return base_record(
        scenario_id,
        "planning_like_nuplan",
        frames,
        OracleRecord(fault_type="planning_collision_risk", root_module="planning", fault_start_time=4.0),
    )


def normal_planning_demo(scenario_id: str) -> ScenarioRecord:
    frames: list[FrameRecord] = []
    for i in range(11):
        t = i * 0.5
        ego = ego_at(t, 5.0)
        actor = front_actor(t, actor_id="veh_002", x0=35.0, vx=5.0)
        trajectory = [TrajectoryPoint(dt=j * 0.5, x=ego.x + j * 2.5, y=3.8, speed=5.0) for j in range(6)]
        frames.append(
            FrameRecord(
                timestamp=t,
                ego=ego,
                actors_gt=[actor],
                actors_gt_source=ActorGtSource.SIMULATION,
                perception=PerceptionState(available=False),
                planning=PlanningState(
                    available=True,
                    trajectory_source=TrajectorySource.OFFLINE_PLANNER,
                    trajectory=trajectory,
                    intent="safe_offset",
                    target_speed=5.0,
                ),
                control=ControlState(available=False),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return base_record(
        scenario_id,
        "planning_like_nuplan",
        frames,
        OracleRecord(fault_type="normal", root_module="none", fault_start_time=None),
    )


def confidence_drop_demo(scenario_id: str) -> ScenarioRecord:
    frames: list[FrameRecord] = []
    for i in range(11):
        t = i * 0.5
        actor = front_actor(t, x0=42.0, vx=6.0)
        confidence = 0.82 if t < 2.5 else 0.24
        frames.append(
            FrameRecord(
                timestamp=t,
                ego=ego_at(t, 6.0),
                actors_gt=[actor],
                actors_gt_source=ActorGtSource.SIMULATION,
                perception=PerceptionState(
                    available=True,
                    detection_source=DetectionSource.SYNTHETIC_FROM_ANNOTATION,
                    detections=[detection_for_actor(actor, confidence)],
                ),
                planning=PlanningState(
                    available=True,
                    trajectory_source=TrajectorySource.MODEL_PREDICTION,
                    trajectory=[TrajectoryPoint(dt=j * 0.5, x=ego_at(t, 6.0).x + j * 3.0, y=0.0, speed=6.0) for j in range(4)],
                    intent="follow",
                    target_speed=6.0,
                ),
                control=ControlState(available=True, steer=0.0, throttle=0.25, brake=0.0),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return base_record(
        scenario_id,
        "full_stack_like_carla",
        frames,
        OracleRecord(fault_type="perception_confidence_drop", root_module="perception", fault_start_time=2.5),
    )


def control_delay_demo(scenario_id: str) -> ScenarioRecord:
    frames: list[FrameRecord] = []
    for i in range(11):
        t = i * 0.5
        ego = ego_at(t, 8.5)
        actor = front_actor(t, x0=24.0, vx=0.0)
        brake = 0.0 if t < 4.5 else 0.35
        trajectory = [TrajectoryPoint(dt=j * 0.5, x=min(ego.x + j * 2.0, 16.0), y=0.0, speed=max(0.0, 6.0 - j)) for j in range(6)]
        frames.append(
            FrameRecord(
                timestamp=t,
                ego=ego,
                actors_gt=[actor],
                actors_gt_source=ActorGtSource.SIMULATION,
                perception=PerceptionState(
                    available=True,
                    detection_source=DetectionSource.SYNTHETIC_FROM_ANNOTATION,
                    detections=[detection_for_actor(actor, 0.86)],
                ),
                planning=PlanningState(
                    available=True,
                    trajectory_source=TrajectorySource.MODEL_PREDICTION,
                    trajectory=trajectory,
                    intent="brake",
                    target_speed=0.0,
                ),
                control=ControlState(available=True, steer=0.0, throttle=0.1, brake=brake),
                map=MapState(available=True, lane_id="lane_01", speed_limit=13.9),
            )
        )
    return base_record(
        scenario_id,
        "full_stack_like_carla",
        frames,
        OracleRecord(fault_type="control_delay", root_module="control", fault_start_time=2.5),
    )


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    scenarios = [
        ("perception_like_nuscenes", perception_miss_demo("manual_v0_1_000001")),
        ("perception_like_nuscenes", false_positive_demo("manual_v0_1_000002")),
        ("planning_like_nuplan", planning_collision_demo("manual_v0_1_000003")),
        ("planning_like_nuplan", normal_planning_demo("manual_v0_1_000004")),
        ("full_stack_like_carla", confidence_drop_demo("manual_v0_1_000005")),
        ("full_stack_like_carla", control_delay_demo("manual_v0_1_000006")),
    ]
    for subset, record in scenarios:
        dump_scenario_record(record, output_dir / subset / f"{record.scenario_id}.json")
    print(f"Generated {len(scenarios)} canonical demo scenarios under {output_dir}")


if __name__ == "__main__":
    main()
