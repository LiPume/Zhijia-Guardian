from __future__ import annotations

import math
import random
from dataclasses import dataclass

from zhijia_guardian.adapters import NuPlanAdapter
from zhijia_guardian.schemas.scenario import (
    OracleRecord,
    ScenarioRecord,
    TrajectorySource,
)
from zhijia_guardian.tools.planning_eval import evaluate_planning


@dataclass(frozen=True)
class CollisionTarget:
    frame_index: int
    point_index: int
    actor_id: str
    actor_x: float
    actor_y: float
    displacement: float


def build_nuplan_perturbation_records(
    adapter: NuPlanAdapter,
    pair_count: int = 5,
    seed: int = 42,
    max_displacement: float = 8.0,
) -> list[ScenarioRecord]:
    if pair_count <= 0:
        raise ValueError("pair_count must be positive")
    rng = random.Random(seed)
    derived: list[ScenarioRecord] = []

    for parent_id in adapter.list_scenarios():
        parent = adapter.load_scenario(parent_id)
        benign = _prepare_candidate(parent, seed, variant="benign")
        if evaluate_planning(benign).trajectory_collision_count != 0:
            continue

        target = _find_collision_target(benign, max_displacement=max_displacement)
        if target is None:
            continue
        faulty = _prepare_candidate(parent, seed, variant="collision")
        _apply_collision_target(faulty, target)
        fault_eval = evaluate_planning(faulty)
        if fault_eval.trajectory_collision_count <= 0:
            continue

        fault_time = faulty.frames[target.frame_index].timestamp
        parent_token = parent.source.raw_tokens.get("scene_token")
        pair_key = str(parent_token or parent_id)
        _set_oracle_and_generation(
            benign,
            fault_type="normal",
            root_module="none",
            fault_time=None,
            generation={
                "benchmark": "nuplan_planning_perturbation_v0_1",
                "seed": seed,
                "parent_scenario_id": parent_id,
                "pair_key": pair_key,
                "variant": "benign",
                "max_lateral_jitter": 0.05,
            },
        )
        _set_oracle_and_generation(
            faulty,
            fault_type="planning_collision_risk",
            root_module="planning",
            fault_time=fault_time,
            generation={
                "benchmark": "nuplan_planning_perturbation_v0_1",
                "seed": seed,
                "parent_scenario_id": parent_id,
                "pair_key": pair_key,
                "variant": "collision",
                "target_actor_id": target.actor_id,
                "target_frame_index": target.frame_index,
                "target_point_index": target.point_index,
                "trajectory_displacement": round(target.displacement, 6),
            },
        )
        derived.extend([benign, faulty])
        if len(derived) >= pair_count * 2:
            break

    if len(derived) < pair_count * 2:
        raise RuntimeError(
            f"Only generated {len(derived) // 2} valid nuPlan pairs; requested {pair_count}"
        )

    rng.shuffle(derived)
    for index, record in enumerate(derived, start=1):
        record.scenario_id = f"nuplan_benchmark_{index:06d}"
    return derived


def _prepare_candidate(parent: ScenarioRecord, seed: int, variant: str) -> ScenarioRecord:
    record = parent.model_copy(deep=True)
    for frame_index, frame in enumerate(record.frames):
        if not frame.planning.available:
            continue
        frame.planning.trajectory_source = TrajectorySource.PERTURBED_PLANNER
        frame.planning.intent = "route_following_candidate"
        lateral_offset = 0.05 * math.sin(seed + frame_index * 0.7)
        cos_yaw = math.cos(frame.ego.yaw)
        sin_yaw = math.sin(frame.ego.yaw)
        for point in frame.planning.trajectory:
            point.x -= lateral_offset * sin_yaw
            point.y += lateral_offset * cos_yaw
    record.source.dataset = "nuplan_perturbation"
    record.source.version = "v0_1"
    record.source.generation = {"variant": variant}
    record.oracle = None
    return record


def _find_collision_target(
    record: ScenarioRecord,
    max_displacement: float,
) -> CollisionTarget | None:
    first_allowed_frame = max(1, len(record.frames) // 4)
    best: CollisionTarget | None = None
    for frame_index, frame in enumerate(record.frames[first_allowed_frame:], start=first_allowed_frame):
        for point_index, point in enumerate(frame.planning.trajectory):
            if point.dt <= 0:
                continue
            for actor in frame.actors_gt:
                actor_x = actor.x + actor.vx * point.dt
                actor_y = actor.y + actor.vy * point.dt
                displacement = math.hypot(point.x - actor_x, point.y - actor_y)
                if best is None or displacement < best.displacement:
                    best = CollisionTarget(
                        frame_index=frame_index,
                        point_index=point_index,
                        actor_id=actor.actor_id,
                        actor_x=actor_x,
                        actor_y=actor_y,
                        displacement=displacement,
                    )
    if best is None or best.displacement > max_displacement:
        return None
    return best


def _apply_collision_target(record: ScenarioRecord, target: CollisionTarget) -> None:
    trajectory = record.frames[target.frame_index].planning.trajectory
    point = trajectory[target.point_index]
    point.x = target.actor_x
    point.y = target.actor_y
    for neighbor_index, weight in [
        (target.point_index - 1, 0.45),
        (target.point_index + 1, 0.45),
    ]:
        if 0 <= neighbor_index < len(trajectory):
            neighbor = trajectory[neighbor_index]
            neighbor.x = (1.0 - weight) * neighbor.x + weight * target.actor_x
            neighbor.y = (1.0 - weight) * neighbor.y + weight * target.actor_y


def _set_oracle_and_generation(
    record: ScenarioRecord,
    fault_type: str,
    root_module: str,
    fault_time: float | None,
    generation: dict[str, object],
) -> None:
    record.source.generation = generation
    record.oracle = OracleRecord(
        fault_type=fault_type,
        root_module=root_module,
        fault_start_time=fault_time,
        fault_segment=(fault_time, fault_time + 0.5) if fault_time is not None else None,
    )
