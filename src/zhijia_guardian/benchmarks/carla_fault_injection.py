from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path

from zhijia_guardian.adapters.carla_adapter import (
    CarlaAdapter,
    CarlaBoundingBox,
    CarlaDetectionSnapshot,
    CarlaLabelFile,
    CarlaRawLog,
    CarlaTransform,
    CarlaVector3D,
)
from zhijia_guardian.schemas.scenario import OracleRecord, TrajectorySource
from zhijia_guardian.utils.io import dump_scenario_jsonl


VARIANTS = (
    "normal",
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "planning_collision_risk",
    "control_delay",
)

V2_VARIANTS = (
    "normal",
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "planning_collision_risk",
    "control_delay",
    "boundary_confidence_normal",
    "boundary_planning_normal",
    "composite_miss_control",
    "composite_confidence_control",
)

V2_ORACLE_LABEL = {
    "normal": "normal",
    "perception_miss": "perception_miss",
    "perception_false_positive": "perception_false_positive",
    "perception_confidence_drop": "perception_confidence_drop",
    "planning_collision_risk": "planning_collision_risk",
    "control_delay": "control_delay",
    "boundary_confidence_normal": "normal",
    "boundary_planning_normal": "normal",
    "composite_miss_control": "perception_miss",
    "composite_confidence_control": "perception_confidence_drop",
}

ROOT_MODULE = {
    "normal": "none",
    "perception_miss": "perception",
    "perception_false_positive": "perception",
    "perception_confidence_drop": "perception",
    "planning_collision_risk": "planning",
    "control_delay": "control",
}


def build_carla_fault_benchmark(
    base_log_dir: str | Path,
    output_root: str | Path,
    *,
    clean: bool = False,
) -> dict:
    base_log_dir = Path(base_log_dir)
    output_root = Path(output_root)
    log_dir = output_root / "raw" / "logs"
    label_dir = output_root / "raw" / "labels"
    canonical_dir = output_root / "canonical"
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)

    base_paths = sorted(base_log_dir.glob("*.json"))
    if not base_paths:
        raise FileNotFoundError(f"no CARLA base logs found in {base_log_dir}")

    manifest_rows = []
    scenario_index = 0
    for parent_index, base_path in enumerate(base_paths, start=1):
        base = _load_raw_log(base_path)
        _validate_base_log(base, base_path)
        for variant in VARIANTS:
            scenario_index += 1
            scenario_id = f"carla_v0_1_{scenario_index:06d}"
            record, fault_start_time = _make_variant(base, variant, scenario_id)
            log_path = log_dir / f"{scenario_index:06d}.json"
            label_path = label_dir / f"{scenario_id}.label.json"
            _dump_model(record, log_path)
            label = CarlaLabelFile(
                scenario_id=scenario_id,
                oracle=OracleRecord(
                    visible_to_diagnosis=False,
                    fault_type=variant,
                    root_module=ROOT_MODULE[variant],
                    fault_start_time=fault_start_time,
                    notes="normal replay" if variant == "normal" else f"offline signal injection: {variant}",
                ),
            )
            _dump_model(label, label_path)
            manifest_rows.append(
                {
                    "scenario_id": scenario_id,
                    "parent_group": f"carla_parent_{parent_index:04d}",
                    "base_log": base_path.name,
                    "variant": variant,
                    "fault_start_time": fault_start_time,
                    "log_file": str(log_path.relative_to(output_root)),
                    "label_file": str(label_path.relative_to(output_root)),
                }
            )

    manifest = {
        "dataset": "carla_fault_injection_v0_1",
        "injection_scope": "offline_signal_level",
        "num_parent_logs": len(base_paths),
        "num_scenarios": len(manifest_rows),
        "variants": list(VARIANTS),
        "scenarios": manifest_rows,
    }
    manifest_path = label_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    adapter = CarlaAdapter(log_dir, label_dir)
    canonical_records = [adapter.load_scenario(scenario_id) for scenario_id in adapter.list_scenarios()]
    dump_scenario_jsonl(canonical_records, canonical_dir / "scenarios.jsonl")
    return manifest


def build_carla_fault_benchmark_v0_2(
    base_log_dir: str | Path,
    output_root: str | Path,
    *,
    seed: int = 42,
    clean: bool = False,
) -> dict:
    base_log_dir = Path(base_log_dir)
    output_root = Path(output_root)
    log_dir = output_root / "raw" / "logs"
    label_dir = output_root / "raw" / "labels"
    canonical_dir = output_root / "canonical"
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)

    base_paths = sorted(base_log_dir.glob("*.json"))
    if not base_paths:
        raise FileNotFoundError(f"no CARLA base logs found in {base_log_dir}")
    parent_splits = _assign_parent_splits(len(base_paths), seed)

    manifest_rows = []
    scenario_index = 0
    for parent_index, base_path in enumerate(base_paths, start=1):
        base = _load_raw_log(base_path)
        _validate_base_log(base, base_path)
        parent_group = f"carla_parent_{parent_index:04d}"
        for variant_index, variant in enumerate(V2_VARIANTS):
            scenario_index += 1
            scenario_id = f"carla_v0_2_{scenario_index:06d}"
            variant_rng = random.Random(seed + parent_index * 1000 + variant_index * 37)
            record, fault_start_time, injection = _make_v2_variant(
                base,
                variant,
                scenario_id,
                variant_rng,
            )
            oracle_label = V2_ORACLE_LABEL[variant]
            log_path = log_dir / f"{scenario_index:06d}.json"
            label_path = label_dir / f"{scenario_id}.label.json"
            _dump_model(record, log_path)
            label = CarlaLabelFile(
                scenario_id=scenario_id,
                oracle=OracleRecord(
                    visible_to_diagnosis=False,
                    fault_type=oracle_label,
                    root_module=ROOT_MODULE[oracle_label],
                    fault_start_time=fault_start_time,
                    notes=f"CARLA v0.2 variant: {variant}",
                ),
            )
            _dump_model(label, label_path)
            manifest_rows.append(
                {
                    "scenario_id": scenario_id,
                    "parent_group": parent_group,
                    "split": parent_splits[parent_index],
                    "base_log": base_path.name,
                    "variant": variant,
                    "oracle_fault_type": oracle_label,
                    "fault_start_time": fault_start_time,
                    "injection": injection,
                    "log_file": str(log_path.relative_to(output_root)),
                    "label_file": str(label_path.relative_to(output_root)),
                }
            )

    manifest = {
        "dataset": "carla_fault_injection_v0_2",
        "injection_scope": "offline_signal_level_randomized",
        "seed": seed,
        "num_parent_logs": len(base_paths),
        "num_scenarios": len(manifest_rows),
        "variants": list(V2_VARIANTS),
        "split_policy": "parent_group_exclusive_60_20_20",
        "scenarios": manifest_rows,
    }
    (label_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    adapter = CarlaAdapter(log_dir, label_dir)
    records_by_id = {scenario_id: adapter.load_scenario(scenario_id) for scenario_id in adapter.list_scenarios()}
    dump_scenario_jsonl(records_by_id.values(), canonical_dir / "scenarios.jsonl")
    for split in ("train", "val", "test"):
        split_ids = [row["scenario_id"] for row in manifest_rows if row["split"] == split]
        if split_ids:
            dump_scenario_jsonl(
                [records_by_id[scenario_id] for scenario_id in split_ids],
                canonical_dir / "splits" / f"{split}.jsonl",
            )
    return manifest


def _load_raw_log(path: Path) -> CarlaRawLog:
    with path.open("r", encoding="utf-8") as f:
        return CarlaRawLog.model_validate(json.load(f))


def _dump_model(model, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _validate_base_log(base: CarlaRawLog, path: Path) -> None:
    if not any(frame.perception.available and frame.perception.detections for frame in base.frames):
        raise ValueError(f"base CARLA log has no perception detections: {path}")
    if not any(frame.planning.available and frame.planning.trajectory for frame in base.frames):
        raise ValueError(f"base CARLA log has no planning trajectory: {path}")
    if not any(frame.control.available for frame in base.frames):
        raise ValueError(f"base CARLA log has no control output: {path}")
    if _key_actor_id(base) is None:
        raise ValueError(f"base CARLA log has no key actor: {path}")


def _make_variant(base: CarlaRawLog, variant: str, scenario_id: str) -> tuple[CarlaRawLog, float | None]:
    record = base.model_copy(deep=True, update={"scenario_id": scenario_id})
    if variant == "normal":
        return record, None

    key_actor_id = _key_actor_id(record)
    if key_actor_id is None:
        raise ValueError("key actor disappeared while copying CARLA log")
    start_index = max(1, len(record.frames) * 2 // 5)
    start_time = record.frames[start_index].simulation_time - record.frames[0].simulation_time

    if variant == "perception_miss":
        for frame in record.frames[start_index:]:
            frame.perception.detections = [
                item for item in frame.perception.detections if item.matched_actor_id != key_actor_id
            ]
    elif variant == "perception_false_positive":
        for frame in record.frames[start_index:]:
            frame.perception.detections.append(_false_positive(frame, key_actor_id))
    elif variant == "perception_confidence_drop":
        for frame in record.frames[start_index:]:
            for detection in frame.perception.detections:
                if detection.matched_actor_id == key_actor_id:
                    detection.confidence = min(detection.confidence, 0.45)
    elif variant == "planning_collision_risk":
        for frame in record.frames[start_index:]:
            target = next((actor for actor in frame.actors if actor.actor_id == key_actor_id), None)
            if target is None or not frame.planning.trajectory:
                continue
            frame.planning.trajectory_source = TrajectorySource.PERTURBED_PLANNER
            frame.planning.trajectory[-1].transform = target.transform.model_copy(deep=True)
            frame.planning.trajectory[-1].speed = max(frame.planning.target_speed or 0.0, 1.0)
    elif variant == "control_delay":
        risk_index, min_ttc = _minimum_ttc(record, key_actor_id)
        if risk_index is None or min_ttc is None or min_ttc >= 1.5:
            raise ValueError("control-delay injection requires a base log with min TTC below 1.5 s")
        start_index = risk_index
        start_time = record.frames[start_index].simulation_time - record.frames[0].simulation_time
        for frame in record.frames[start_index:]:
            if frame.control.available:
                frame.control.brake = 0.0
    else:
        raise ValueError(f"unsupported CARLA fault variant: {variant}")
    return record, round(start_time, 6)


def _make_v2_variant(
    base: CarlaRawLog,
    variant: str,
    scenario_id: str,
    rng: random.Random,
) -> tuple[CarlaRawLog, float | None, dict]:
    record = base.model_copy(deep=True, update={"scenario_id": scenario_id})
    if variant == "normal":
        return record, None, {"kind": "unaltered_replay"}

    key_actor_id = _key_actor_id(record)
    if key_actor_id is None:
        raise ValueError("key actor disappeared while copying CARLA log")
    default_start = max(1, len(record.frames) * 3 // 10)
    max_duration = max(3, len(record.frames) - default_start)
    duration = rng.randint(3, min(8, max_duration))

    if variant == "perception_miss":
        start = default_start + rng.randint(0, max(0, len(record.frames) // 10))
        duration = min(duration, len(record.frames) - start)
        _inject_miss(record, key_actor_id, start, duration)
        return record, _relative_time(record, start), {"kind": variant, "duration_frames": duration}

    if variant == "perception_false_positive":
        start = default_start
        duration = min(duration, len(record.frames) - start)
        for frame in record.frames[start : start + duration]:
            frame.perception.detections.append(_false_positive(frame, key_actor_id))
        return record, _relative_time(record, start), {"kind": variant, "duration_frames": duration}

    if variant == "perception_confidence_drop":
        start = default_start
        duration = min(duration, len(record.frames) - start)
        target_confidence = round(rng.uniform(0.38, 0.52), 3)
        _inject_confidence(record, key_actor_id, start, duration, target_confidence)
        return record, _relative_time(record, start), {
            "kind": variant,
            "duration_frames": duration,
            "target_confidence": target_confidence,
        }

    if variant == "planning_collision_risk":
        start = default_start
        duration = min(duration, len(record.frames) - start)
        _inject_planning_collision(record, key_actor_id, start, duration)
        return record, _relative_time(record, start), {"kind": variant, "duration_frames": duration}

    if variant == "control_delay":
        delay = round(rng.uniform(0.7, 1.0), 3)
        start = _inject_control_delay(record, key_actor_id, delay)
        return record, _relative_time(record, start), {"kind": variant, "delay_seconds": delay}

    if variant == "boundary_confidence_normal":
        start = default_start
        duration = min(duration, len(record.frames) - start)
        target_confidence = 0.64
        _inject_confidence(record, key_actor_id, start, duration, target_confidence)
        return record, None, {
            "kind": variant,
            "duration_frames": duration,
            "target_confidence": target_confidence,
            "expected": "below confidence-drop threshold",
        }

    if variant == "boundary_planning_normal":
        start = default_start
        duration = min(duration, len(record.frames) - start)
        clearance = round(rng.uniform(0.56, 0.72), 3)
        _inject_boundary_planning(record, key_actor_id, start, duration, clearance)
        return record, None, {
            "kind": variant,
            "duration_frames": duration,
            "clearance_m": clearance,
            "expected": "above planning collision margin",
        }

    risk_index, risk_ttc = _first_ttc_below(record, key_actor_id)
    if risk_index is None or risk_ttc is None:
        raise ValueError(f"{variant} requires a base log with min TTC below 1.5 s")
    perception_start = max(1, risk_index - rng.randint(4, 6))
    delay = round(rng.uniform(0.7, 1.0), 3)
    _inject_control_delay(record, key_actor_id, delay)
    if variant == "composite_miss_control":
        _inject_miss(record, key_actor_id, perception_start, len(record.frames) - perception_start)
        return record, _relative_time(record, perception_start), {
            "kind": variant,
            "primary_fault": "perception_miss",
            "downstream_fault": "control_delay",
            "control_delay_seconds": delay,
        }
    if variant == "composite_confidence_control":
        target_confidence = round(rng.uniform(0.4, 0.5), 3)
        _inject_confidence(
            record,
            key_actor_id,
            perception_start,
            len(record.frames) - perception_start,
            target_confidence,
        )
        return record, _relative_time(record, perception_start), {
            "kind": variant,
            "primary_fault": "perception_confidence_drop",
            "downstream_fault": "control_delay",
            "target_confidence": target_confidence,
            "control_delay_seconds": delay,
        }
    raise ValueError(f"unsupported CARLA v0.2 variant: {variant}")


def _inject_miss(record: CarlaRawLog, actor_id: int, start: int, duration: int) -> None:
    for frame in record.frames[start : start + duration]:
        frame.perception.detections = [
            item for item in frame.perception.detections if item.matched_actor_id != actor_id
        ]


def _inject_confidence(
    record: CarlaRawLog,
    actor_id: int,
    start: int,
    duration: int,
    target_confidence: float,
) -> None:
    for frame in record.frames[start : start + duration]:
        for detection in frame.perception.detections:
            if detection.matched_actor_id == actor_id:
                detection.confidence = min(detection.confidence, target_confidence)


def _inject_planning_collision(record: CarlaRawLog, actor_id: int, start: int, duration: int) -> None:
    for frame in record.frames[start : start + duration]:
        target = next((actor for actor in frame.actors if actor.actor_id == actor_id), None)
        if target is None or not frame.planning.trajectory:
            continue
        frame.planning.trajectory_source = TrajectorySource.PERTURBED_PLANNER
        frame.planning.trajectory[-1].transform = target.transform.model_copy(deep=True)
        frame.planning.trajectory[-1].speed = max(frame.planning.target_speed or 0.0, 1.0)


def _inject_boundary_planning(
    record: CarlaRawLog,
    actor_id: int,
    start: int,
    duration: int,
    clearance: float,
) -> None:
    for frame in record.frames[start : start + duration]:
        target = next((actor for actor in frame.actors if actor.actor_id == actor_id), None)
        if target is None or not frame.planning.trajectory:
            continue
        target_point = target.transform.model_copy(deep=True)
        yaw = math.radians(target.transform.rotation.yaw)
        center_distance = (
            target.bounding_box.extent.x + frame.ego.bounding_box.extent.x + clearance
        )
        target_point.location.x -= math.cos(yaw) * center_distance
        target_point.location.y -= math.sin(yaw) * center_distance
        frame.planning.trajectory_source = TrajectorySource.PERTURBED_PLANNER
        frame.planning.trajectory[-1].transform = target_point
        frame.planning.trajectory[-1].speed = 0.0


def _inject_control_delay(record: CarlaRawLog, actor_id: int, delay_seconds: float) -> int:
    risk_index, risk_ttc = _first_ttc_below(record, actor_id)
    if risk_index is None or risk_ttc is None:
        raise ValueError("control-delay injection requires a base log with min TTC below 1.5 s")
    risk_time = record.frames[risk_index].simulation_time
    end_time = risk_time + delay_seconds
    for frame in record.frames[risk_index:]:
        if frame.simulation_time >= end_time:
            break
        if frame.control.available:
            frame.control.brake = 0.0
    return risk_index


def _relative_time(record: CarlaRawLog, frame_index: int) -> float:
    return round(
        record.frames[frame_index].simulation_time - record.frames[0].simulation_time,
        6,
    )


def _assign_parent_splits(num_parents: int, seed: int) -> dict[int, str]:
    indices = list(range(1, num_parents + 1))
    random.Random(seed).shuffle(indices)
    if num_parents == 1:
        return {indices[0]: "test"}
    test_count = max(1, round(num_parents * 0.2))
    val_count = max(1, round(num_parents * 0.2)) if num_parents >= 3 else 0
    split_by_parent = {}
    for position, parent_index in enumerate(indices):
        if position < test_count:
            split = "test"
        elif position < test_count + val_count:
            split = "val"
        else:
            split = "train"
        split_by_parent[parent_index] = split
    return split_by_parent


def _key_actor_id(record: CarlaRawLog) -> int | None:
    for frame in record.frames:
        for actor in frame.actors:
            if actor.is_key_actor:
                return actor.actor_id
    return None


def _false_positive(frame, key_actor_id: int) -> CarlaDetectionSnapshot:
    key_actor = next((actor for actor in frame.actors if actor.actor_id == key_actor_id), None)
    if key_actor is None:
        bbox = CarlaBoundingBox(extent=CarlaVector3D(x=2.2, y=0.9, z=0.8))
    else:
        bbox = key_actor.bounding_box.model_copy(deep=True)
    ego_location = frame.ego.transform.location
    transform = CarlaTransform(
        location=CarlaVector3D(x=ego_location.x + 30.0, y=ego_location.y + 30.0, z=ego_location.z),
        rotation=frame.ego.transform.rotation.model_copy(deep=True),
    )
    return CarlaDetectionSnapshot(
        track_id=f"injected_fp_{frame.frame_id}",
        type="vehicle",
        confidence=0.88,
        transform=transform,
        bounding_box=bbox,
        matched_actor_id=None,
    )


def _minimum_ttc(record: CarlaRawLog, actor_id: int) -> tuple[int | None, float | None]:
    best_index: int | None = None
    best_ttc: float | None = None
    for index, frame in enumerate(record.frames):
        actor = next((item for item in frame.actors if item.actor_id == actor_id), None)
        if actor is None:
            continue
        ego = frame.ego
        yaw = math.radians(ego.transform.rotation.yaw)
        heading_x, heading_y = math.cos(yaw), math.sin(yaw)
        dx = actor.transform.location.x - ego.transform.location.x
        dy = actor.transform.location.y - ego.transform.location.y
        longitudinal = dx * heading_x + dy * heading_y
        lateral = -dx * heading_y + dy * heading_x
        ego_speed = ego.velocity.x * heading_x + ego.velocity.y * heading_y
        actor_speed = actor.velocity.x * heading_x + actor.velocity.y * heading_y
        closing_speed = ego_speed - actor_speed
        if longitudinal <= 0.0 or abs(lateral) > 3.0 or closing_speed <= 0.1:
            continue
        ttc = longitudinal / closing_speed
        if best_ttc is None or ttc < best_ttc:
            best_index, best_ttc = index, ttc
    return best_index, best_ttc


def _first_ttc_below(
    record: CarlaRawLog,
    actor_id: int,
    threshold: float = 1.5,
) -> tuple[int | None, float | None]:
    for index, frame in enumerate(record.frames):
        actor = next((item for item in frame.actors if item.actor_id == actor_id), None)
        if actor is None:
            continue
        ego = frame.ego
        yaw = math.radians(ego.transform.rotation.yaw)
        heading_x, heading_y = math.cos(yaw), math.sin(yaw)
        dx = actor.transform.location.x - ego.transform.location.x
        dy = actor.transform.location.y - ego.transform.location.y
        longitudinal = dx * heading_x + dy * heading_y
        lateral = -dx * heading_y + dy * heading_x
        ego_speed = ego.velocity.x * heading_x + ego.velocity.y * heading_y
        actor_speed = actor.velocity.x * heading_x + actor.velocity.y * heading_y
        closing_speed = ego_speed - actor_speed
        if longitudinal <= 0.0 or abs(lateral) > 3.0 or closing_speed <= 0.1:
            continue
        ttc = longitudinal / closing_speed
        if ttc < threshold:
            return index, ttc
    return None, None
