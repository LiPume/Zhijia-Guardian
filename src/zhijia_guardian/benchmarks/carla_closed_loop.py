from __future__ import annotations

import json
import math
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from zhijia_guardian.adapters import CarlaAdapter
from zhijia_guardian.adapters.carla_adapter import CarlaLabelFile, CarlaRawLog
from zhijia_guardian.schemas.scenario import OracleRecord
from zhijia_guardian.utils.io import dump_scenario_jsonl


CLOSED_LOOP_CASES = ("normal", "control_delay", "planning_collision_risk")
ROOT_MODULE = {
    "normal": "none",
    "control_delay": "control",
    "planning_collision_risk": "planning",
}


def record_carla_closed_loop_benchmark(
    output_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 2000,
    town: str = "Town10HD_Opt",
    parent_count: int = 5,
    seed: int = 42,
    fixed_delta_seconds: float = 0.1,
    max_frames: int = 80,
    lead_distance: float = 18.0,
    target_speed: float = 7.0,
    control_delay: float = 0.8,
    planning_fault_start: float = 0.5,
    no_rendering: bool = True,
    clean: bool = False,
) -> dict:
    try:
        import carla
    except ImportError as exc:
        raise RuntimeError("carla==0.9.15 is required to record closed-loop scenarios") from exc

    output_root = Path(output_root)
    log_dir = output_root / "raw" / "logs"
    label_dir = output_root / "raw" / "labels"
    canonical_dir = output_root / "canonical"
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    canonical_dir.mkdir(parents=True, exist_ok=True)

    client = carla.Client(host, port)
    client.set_timeout(30.0)
    world = client.get_world()
    if not world.get_map().name.endswith(f"/{town}"):
        raise RuntimeError(
            f"CARLA is running {world.get_map().name}; start a fresh server on {town} to avoid hot reload"
        )
    spawn_points = _eligible_spawn_points(world.get_map(), lead_distance)
    rng = random.Random(seed)
    rng.shuffle(spawn_points)
    if len(spawn_points) < parent_count:
        raise RuntimeError(f"only {len(spawn_points)} spawn points support lead distance {lead_distance}")
    split_by_parent = _assign_parent_splits(parent_count, seed)

    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = fixed_delta_seconds
    settings.no_rendering_mode = no_rendering
    world.apply_settings(settings)
    manifest_rows = []
    scenario_index = 0
    try:
        for parent_index, spawn_transform in enumerate(spawn_points[:parent_count], start=1):
            for case_name in CLOSED_LOOP_CASES:
                scenario_index += 1
                scenario_id = f"carla_cl_v0_1_{scenario_index:06d}"
                raw_log, outcome = _record_case(
                    carla,
                    world,
                    spawn_transform,
                    scenario_id,
                    case_name,
                    fixed_delta_seconds=fixed_delta_seconds,
                    max_frames=max_frames,
                    lead_distance=lead_distance,
                    target_speed=target_speed,
                    control_delay=control_delay,
                    planning_fault_start=planning_fault_start,
                )
                log_path = log_dir / f"{scenario_index:06d}.json"
                label_path = label_dir / f"{scenario_id}.label.json"
                _dump_model(raw_log, log_path)
                _dump_model(
                    CarlaLabelFile(
                        scenario_id=scenario_id,
                        oracle=OracleRecord(
                            visible_to_diagnosis=False,
                            fault_type=case_name,
                            root_module=ROOT_MODULE[case_name],
                            fault_start_time=outcome["fault_start_time"],
                            notes=f"CARLA closed-loop case: {case_name}",
                        ),
                    ),
                    label_path,
                )
                manifest_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "parent_group": f"carla_cl_parent_{parent_index:04d}",
                        "split": split_by_parent[parent_index],
                        "case": case_name,
                        "outcome": outcome,
                        "log_file": str(log_path.relative_to(output_root)),
                        "label_file": str(label_path.relative_to(output_root)),
                    }
                )
    finally:
        world.apply_settings(original_settings)

    manifest = {
        "dataset": "carla_closed_loop_v0_1",
        "carla_version": client.get_server_version(),
        "map": world.get_map().name,
        "seed": seed,
        "num_parent_logs": parent_count,
        "num_scenarios": len(manifest_rows),
        "cases": list(CLOSED_LOOP_CASES),
        "fixed_delta_seconds": fixed_delta_seconds,
        "control_delay_seconds": control_delay,
        "planning_fault_start_seconds": planning_fault_start,
        "split_policy": "parent_group_exclusive_60_20_20",
        "scenarios": manifest_rows,
    }
    (label_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    adapter = CarlaAdapter(log_dir, label_dir)
    records = {scenario_id: adapter.load_scenario(scenario_id) for scenario_id in adapter.list_scenarios()}
    dump_scenario_jsonl(records.values(), canonical_dir / "scenarios.jsonl")
    for split in ("train", "val", "test"):
        split_ids = [row["scenario_id"] for row in manifest_rows if row["split"] == split]
        if split_ids:
            dump_scenario_jsonl(
                [records[scenario_id] for scenario_id in split_ids],
                canonical_dir / "splits" / f"{split}.jsonl",
            )
    return manifest


def _record_case(
    carla,
    world,
    spawn_transform,
    scenario_id: str,
    case_name: str,
    *,
    fixed_delta_seconds: float,
    max_frames: int,
    lead_distance: float,
    target_speed: float,
    control_delay: float,
    planning_fault_start: float,
) -> tuple[CarlaRawLog, dict]:
    actors = []
    sensors = []
    event_buffer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    collision_state = {"occurred": False, "frame": None, "other_actor": None}
    try:
        library = world.get_blueprint_library()
        ego_blueprint = _vehicle_blueprint(library, "vehicle.tesla.model3", "hero", "30,90,230")
        lead_blueprint = _vehicle_blueprint(
            library,
            "vehicle.lincoln.mkz_2020",
            "scenario",
            "220,40,40",
        )
        ego = world.try_spawn_actor(ego_blueprint, _raised_transform(carla, spawn_transform))
        if ego is None:
            raise RuntimeError(f"failed to spawn ego for {scenario_id}")
        actors.append(ego)
        ego_waypoint = world.get_map().get_waypoint(spawn_transform.location, project_to_road=True)
        lead_waypoint = _choose_waypoint(ego_waypoint.next(lead_distance))
        lead = world.try_spawn_actor(lead_blueprint, _raised_transform(carla, lead_waypoint.transform))
        if lead is None:
            raise RuntimeError(f"failed to spawn lead actor for {scenario_id}")
        actors.append(lead)
        lead.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, hand_brake=True))

        collision_sensor = world.spawn_actor(
            library.find("sensor.other.collision"),
            carla.Transform(),
            attach_to=ego,
        )
        collision_sensor.listen(
            lambda event: _capture_collision(event_buffer, collision_state, event)
        )
        sensors.append(collision_sensor)
        lane_sensor = world.spawn_actor(
            library.find("sensor.other.lane_invasion"),
            carla.Transform(),
            attach_to=ego,
        )
        lane_sensor.listen(lambda event: _capture_lane_invasion(event_buffer, event))
        sensors.append(lane_sensor)

        for _ in range(5):
            world.tick()
        forward = ego.get_transform().get_forward_vector()
        ego.set_target_velocity(
            carla.Vector3D(x=forward.x * target_speed, y=forward.y * target_speed)
        )
        world.tick()

        raw_frames = []
        first_capture_time = None
        risk_start_abs = None
        planning_fault_abs = None
        brake_start_abs = None
        min_ttc = None
        stopped_frames = 0
        collision_followup = 0
        braking_started = False
        for _ in range(max_frames):
            pre_snapshot = world.get_snapshot()
            pre_time = pre_snapshot.timestamp.elapsed_seconds
            if first_capture_time is None:
                first_capture_time = pre_time + fixed_delta_seconds
            _, ttc, speed = _risk_state(ego, lead)
            if ttc is not None:
                min_ttc = ttc if min_ttc is None else min(min_ttc, ttc)
            if risk_start_abs is None and ttc is not None and ttc < 1.5:
                risk_start_abs = pre_time

            elapsed = pre_time - first_capture_time
            planning_active = (
                case_name == "planning_collision_risk" and elapsed >= planning_fault_start
            )
            braking_started = braking_started or (ttc is not None and ttc < 1.5)
            should_brake = braking_started
            if case_name == "control_delay" and risk_start_abs is not None:
                braking_started = pre_time - risk_start_abs >= control_delay
                should_brake = braking_started
            elif case_name == "planning_collision_risk" and planning_active:
                braking_started = False
                should_brake = False
            if should_brake and brake_start_abs is None:
                brake_start_abs = pre_time

            control = _drive_control(carla, ego, target_speed, should_brake)
            ego.apply_control(control)
            frame_id = world.tick()
            snapshot = world.get_snapshot()
            simulation_time = snapshot.timestamp.elapsed_seconds
            if planning_active and planning_fault_abs is None:
                planning_fault_abs = simulation_time
            _, current_ttc, current_speed = _risk_state(ego, lead)
            if current_ttc is not None:
                min_ttc = current_ttc if min_ttc is None else min(min_ttc, current_ttc)
            raw_frames.append(
                _snapshot_frame(
                    world,
                    frame_id,
                    simulation_time,
                    ego,
                    lead,
                    control,
                    event_buffer.pop(frame_id, []),
                    target_speed,
                    unsafe_planning=planning_active,
                )
            )

            stopped_frames = stopped_frames + 1 if should_brake and current_speed < 0.2 else 0
            collision_followup = collision_followup + 1 if collision_state["occurred"] else 0
            if stopped_frames >= 8 or collision_followup >= 10:
                break

        for frame in raw_frames:
            frame["events"].extend(event_buffer.pop(frame["frame_id"], []))
        raw_log = CarlaRawLog.model_validate(
            {
                "log_version": "carla_log_v0_1",
                "scenario_id": scenario_id,
                "carla_version": "0.9.15",
                "map_name": world.get_map().name,
                "fixed_delta_seconds": fixed_delta_seconds,
                "frames": raw_frames,
            }
        )
        first_raw_time = raw_log.frames[0].simulation_time
        if case_name == "control_delay":
            fault_start_abs = risk_start_abs
        elif case_name == "planning_collision_risk":
            fault_start_abs = planning_fault_abs
        else:
            fault_start_abs = None
        fault_start_time = (
            None
            if fault_start_abs is None
            else round(max(0.0, fault_start_abs - first_raw_time), 6)
        )
        return raw_log, {
            "fault_start_time": fault_start_time,
            "risk_start_time": _relative_optional(risk_start_abs, first_raw_time),
            "brake_start_time": _relative_optional(brake_start_abs, first_raw_time),
            "min_ttc": None if min_ttc is None else round(min_ttc, 3),
            "collision": collision_state["occurred"],
            "collision_frame": collision_state["frame"],
            "collision_with": collision_state["other_actor"],
            "num_frames": len(raw_frames),
        }
    finally:
        for sensor in sensors:
            sensor.stop()
            sensor.destroy()
        for actor in reversed(actors):
            actor.destroy()
        world.tick()


def _snapshot_frame(
    world,
    frame_id: int,
    simulation_time: float,
    ego,
    lead,
    control,
    events: list[dict[str, Any]],
    target_speed: float,
    *,
    unsafe_planning: bool,
) -> dict:
    ego_snapshot = _actor_snapshot(ego, is_key_actor=False)
    lead_snapshot = _actor_snapshot(lead, is_key_actor=True)
    waypoint = world.get_map().get_waypoint(ego.get_location(), project_to_road=True)
    return {
        "frame_id": frame_id,
        "simulation_time": simulation_time,
        "ego": ego_snapshot,
        "actors": [lead_snapshot],
        "perception": {
            "available": True,
            "detection_source": "synthetic_from_annotation",
            "detections": [_synthetic_detection(lead_snapshot)],
        },
        "planning": {
            "available": True,
            "trajectory_source": "perturbed_planner" if unsafe_planning else "offline_planner",
            "trajectory": _trajectory(world.get_map(), ego, lead, unsafe=unsafe_planning),
            "intent": "continue_into_obstacle" if unsafe_planning else "stop_for_lead_vehicle",
            "target_speed": target_speed,
        },
        "control": {
            "available": True,
            "steer": control.steer,
            "throttle": control.throttle,
            "brake": control.brake,
        },
        "map": {
            "available": waypoint is not None,
            "lane_id": f"{waypoint.road_id}:{waypoint.lane_id}" if waypoint is not None else None,
            "road_id": waypoint.road_id if waypoint is not None else None,
            "speed_limit": ego.get_speed_limit() / 3.6,
        },
        "events": events,
    }


def _trajectory(carla_map, ego, lead, *, unsafe: bool) -> list[dict[str, Any]]:
    ego_transform = ego.get_transform()
    speed = _speed(ego.get_velocity())
    waypoint = carla_map.get_waypoint(ego_transform.location, project_to_road=True)
    if unsafe:
        lead_transform = lead.get_transform()
        lead_velocity = lead.get_velocity()
        lead_transform.location.x += lead_velocity.x
        lead_transform.location.y += lead_velocity.y
        points = [
            {"dt": 0.0, "transform": _transform_dict(ego_transform), "speed": speed},
            {"dt": 1.0, "transform": _transform_dict(lead_transform), "speed": max(speed, 1.0)},
        ]
        return points

    center_distance = ego_transform.location.distance(lead.get_location())
    half_length_sum = ego.bounding_box.extent.x + lead.bounding_box.extent.x
    safe_travel = max(center_distance - half_length_sum - 1.5, 0.0)
    points = []
    for dt in (0.0, 0.5, 1.0, 1.5, 2.0):
        travel = min(speed * dt, safe_travel)
        target_waypoint = waypoint if travel <= 0.01 else _choose_waypoint(waypoint.next(travel))
        target_transform = target_waypoint.transform if target_waypoint is not None else ego_transform
        points.append(
            {
                "dt": dt,
                "transform": _transform_dict(target_transform),
                "speed": speed if travel < safe_travel else 0.0,
            }
        )
    return points


def _drive_control(carla, ego, target_speed: float, should_brake: bool):
    transform = ego.get_transform()
    waypoint = ego.get_world().get_map().get_waypoint(transform.location, project_to_road=True)
    next_waypoints = waypoint.next(3.0)
    target_waypoint = next_waypoints[0] if next_waypoints else waypoint
    steer = _steer_to_waypoint(transform, target_waypoint)
    if should_brake:
        return carla.VehicleControl(steer=steer, throttle=0.0, brake=0.85)
    speed = _speed(ego.get_velocity())
    throttle = min(0.5, max(0.0, 0.2 + 0.08 * (target_speed - speed)))
    return carla.VehicleControl(steer=steer, throttle=throttle, brake=0.0)


def _risk_state(ego, lead) -> tuple[float, float | None, float]:
    transform = ego.get_transform()
    forward = transform.get_forward_vector()
    dx = lead.get_location().x - transform.location.x
    dy = lead.get_location().y - transform.location.y
    gap = dx * forward.x + dy * forward.y
    ego_velocity = ego.get_velocity()
    lead_velocity = lead.get_velocity()
    closing_speed = (
        ego_velocity.x * forward.x
        + ego_velocity.y * forward.y
        - lead_velocity.x * forward.x
        - lead_velocity.y * forward.y
    )
    ttc = gap / closing_speed if gap > 0.0 and closing_speed > 0.1 else None
    return gap, ttc, _speed(ego_velocity)


def _actor_snapshot(actor, *, is_key_actor: bool) -> dict[str, Any]:
    return {
        "actor_id": actor.id,
        "type_id": actor.type_id,
        "transform": _transform_dict(actor.get_transform()),
        "velocity": _vector_dict(actor.get_velocity()),
        "acceleration": _vector_dict(actor.get_acceleration()),
        "bounding_box": {"extent": _vector_dict(actor.bounding_box.extent)},
        "is_key_actor": is_key_actor,
    }


def _synthetic_detection(actor_snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_id": f"det_{actor_snapshot['actor_id']}",
        "type": "vehicle",
        "confidence": 0.95,
        "transform": actor_snapshot["transform"],
        "bounding_box": actor_snapshot["bounding_box"],
        "matched_actor_id": actor_snapshot["actor_id"],
    }


def _capture_collision(buffer, state: dict, event) -> None:
    impulse = event.normal_impulse
    state["occurred"] = True
    state["frame"] = event.frame
    state["other_actor"] = event.other_actor.type_id
    buffer[event.frame].append(
        {
            "event_type": "collision",
            "description": f"Collision with {event.other_actor.type_id}",
            "attributes": {
                "other_actor_id": event.other_actor.id,
                "other_actor_type": event.other_actor.type_id,
                "impulse": round(_speed(impulse), 6),
            },
        }
    )


def _capture_lane_invasion(buffer, event) -> None:
    buffer[event.frame].append(
        {
            "event_type": "lane_invasion",
            "description": "Ego crossed a lane marking",
            "attributes": {
                "marking_types": ",".join(str(item.type) for item in event.crossed_lane_markings)
            },
        }
    )


def _eligible_spawn_points(carla_map, lead_distance: float) -> list[Any]:
    return [
        transform
        for transform in carla_map.get_spawn_points()
        if carla_map.get_waypoint(transform.location, project_to_road=True).next(lead_distance)
    ]


def _assign_parent_splits(num_parents: int, seed: int) -> dict[int, str]:
    indices = list(range(1, num_parents + 1))
    random.Random(seed).shuffle(indices)
    test_count = max(1, round(num_parents * 0.2))
    val_count = max(1, round(num_parents * 0.2)) if num_parents >= 3 else 0
    result = {}
    for position, parent_index in enumerate(indices):
        if position < test_count:
            result[parent_index] = "test"
        elif position < test_count + val_count:
            result[parent_index] = "val"
        else:
            result[parent_index] = "train"
    return result


def _vehicle_blueprint(library, blueprint_id: str, role_name: str, color: str):
    blueprint = library.find(blueprint_id)
    if blueprint.has_attribute("role_name"):
        blueprint.set_attribute("role_name", role_name)
    if blueprint.has_attribute("color"):
        blueprint.set_attribute("color", color)
    return blueprint


def _raised_transform(carla, transform):
    result = carla.Transform(transform.location, transform.rotation)
    result.location.z += 0.3
    return result


def _choose_waypoint(waypoints):
    if not waypoints:
        return None
    return sorted(waypoints, key=lambda item: (item.road_id, item.lane_id, item.s))[0]


def _steer_to_waypoint(ego_transform, waypoint) -> float:
    target = waypoint.transform.location
    desired_yaw = math.degrees(
        math.atan2(target.y - ego_transform.location.y, target.x - ego_transform.location.x)
    )
    error = (desired_yaw - ego_transform.rotation.yaw + 180.0) % 360.0 - 180.0
    return max(-0.6, min(0.6, error / 45.0))


def _transform_dict(transform) -> dict[str, Any]:
    return {
        "location": _vector_dict(transform.location),
        "rotation": {
            "pitch": transform.rotation.pitch,
            "yaw": transform.rotation.yaw,
            "roll": transform.rotation.roll,
        },
    }


def _vector_dict(vector) -> dict[str, float]:
    return {"x": vector.x, "y": vector.y, "z": vector.z}


def _speed(vector) -> float:
    return math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)


def _relative_optional(value: float | None, first_time: float) -> float | None:
    return None if value is None else round(max(0.0, value - first_time), 6)


def _dump_model(model, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
