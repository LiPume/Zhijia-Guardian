#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from zhijia_guardian.adapters.carla_adapter import CarlaRawLog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record deterministic CARLA lead-vehicle base scenarios.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--town", default="Town03")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--frames", type=int, default=80)
    parser.add_argument("--fixed-delta", type=float, default=0.1)
    parser.add_argument("--lead-distance", type=float, default=18.0)
    parser.add_argument("--target-speed", type=float, default=7.0, help="Target ego speed in m/s.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--no-rendering", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        import carla
    except ImportError as exc:
        raise SystemExit(
            "CARLA Python API is unavailable. Install the wheel bundled with the matching CARLA release."
        ) from exc

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world = client.load_world(args.town)
    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = args.fixed_delta
    settings.no_rendering_mode = args.no_rendering
    world.apply_settings(settings)

    try:
        spawn_points = _eligible_spawn_points(world.get_map(), args.lead_distance)
        rng = random.Random(args.seed)
        rng.shuffle(spawn_points)
        if len(spawn_points) < args.count:
            raise RuntimeError(f"only {len(spawn_points)} spawn points support a lead actor")
        for index, ego_transform in enumerate(spawn_points[: args.count], start=1):
            raw_log = _record_one(carla, world, ego_transform, index, args, rng)
            path = output_dir / f"base_{index:06d}.json"
            path.write_text(
                json.dumps(raw_log.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"recorded {path} ({len(raw_log.frames)} frames)", flush=True)
    finally:
        world.apply_settings(original_settings)


def _eligible_spawn_points(carla_map, lead_distance: float) -> list[Any]:
    eligible = []
    for transform in carla_map.get_spawn_points():
        waypoint = carla_map.get_waypoint(transform.location, project_to_road=True)
        if waypoint is not None and waypoint.next(lead_distance):
            eligible.append(transform)
    return eligible


def _record_one(carla, world, ego_transform, index: int, args: argparse.Namespace, rng: random.Random):
    actors = []
    sensors = []
    event_buffer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    try:
        blueprint_library = world.get_blueprint_library()
        ego_blueprint = _vehicle_blueprint(blueprint_library, "vehicle.tesla.model3", "hero")
        lead_blueprint = _vehicle_blueprint(blueprint_library, "vehicle.lincoln.mkz_2020", "scenario")
        ego = world.try_spawn_actor(ego_blueprint, _raised_transform(carla, ego_transform))
        if ego is None:
            raise RuntimeError(f"failed to spawn ego for scenario {index}")
        actors.append(ego)

        ego_waypoint = world.get_map().get_waypoint(ego_transform.location, project_to_road=True)
        lead_waypoint = _choose_waypoint(ego_waypoint.next(args.lead_distance))
        lead = world.try_spawn_actor(lead_blueprint, _raised_transform(carla, lead_waypoint.transform))
        if lead is None:
            raise RuntimeError(f"failed to spawn lead actor for scenario {index}")
        actors.append(lead)
        lead.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, hand_brake=True))

        collision_sensor = world.spawn_actor(
            blueprint_library.find("sensor.other.collision"), carla.Transform(), attach_to=ego
        )
        collision_sensor.listen(lambda event: _capture_collision(event_buffer, event))
        sensors.append(collision_sensor)
        lane_sensor = world.spawn_actor(
            blueprint_library.find("sensor.other.lane_invasion"), carla.Transform(), attach_to=ego
        )
        lane_sensor.listen(lambda event: _capture_lane_invasion(event_buffer, event))
        sensors.append(lane_sensor)

        for _ in range(5):
            world.tick()
        forward = ego.get_transform().get_forward_vector()
        ego.set_target_velocity(carla.Vector3D(x=forward.x * args.target_speed, y=forward.y * args.target_speed))
        world.tick()

        raw_frames = []
        braking_started = False
        stopped_frames = 0
        for _ in range(args.frames):
            control, braking_started = _normal_control(carla, ego, lead, args.target_speed, braking_started)
            ego.apply_control(control)
            frame_id = world.tick()
            snapshot = world.get_snapshot()
            raw_frames.append(
                _snapshot_frame(
                    world,
                    frame_id,
                    snapshot.timestamp.elapsed_seconds,
                    ego,
                    lead,
                    control,
                    event_buffer.pop(frame_id, []),
                    rng,
                    args.target_speed,
                )
            )
            speed = _speed(ego.get_velocity())
            stopped_frames = stopped_frames + 1 if braking_started and speed < 0.2 else 0
            if stopped_frames >= 8:
                break

        for frame in raw_frames:
            frame["events"].extend(event_buffer.pop(frame["frame_id"], []))
        return CarlaRawLog.model_validate(
            {
                "log_version": "carla_log_v0_1",
                "scenario_id": f"carla_base_{index:06d}",
                "carla_version": "0.9.15",
                "map_name": world.get_map().name,
                "fixed_delta_seconds": args.fixed_delta,
                "frames": raw_frames,
            }
        )
    finally:
        for sensor in sensors:
            sensor.stop()
            sensor.destroy()
        for actor in reversed(actors):
            actor.destroy()
        world.tick()


def _normal_control(carla, ego, lead, target_speed: float, braking_started: bool):
    ego_transform = ego.get_transform()
    lead_location = lead.get_location()
    dx = lead_location.x - ego_transform.location.x
    dy = lead_location.y - ego_transform.location.y
    forward = ego_transform.get_forward_vector()
    longitudinal_gap = dx * forward.x + dy * forward.y
    speed = _speed(ego.get_velocity())
    ttc = longitudinal_gap / speed if speed > 0.2 and longitudinal_gap > 0.0 else math.inf
    braking_started = braking_started or ttc <= 1.25 or longitudinal_gap <= 8.0
    waypoint = ego.get_world().get_map().get_waypoint(ego_transform.location, project_to_road=True)
    steer = _steer_to_waypoint(ego_transform, waypoint.next(3.0)[0] if waypoint.next(3.0) else waypoint)
    if braking_started:
        return carla.VehicleControl(steer=steer, throttle=0.0, brake=0.85), True
    throttle = min(0.55, max(0.15, 0.25 + 0.08 * (target_speed - speed)))
    return carla.VehicleControl(steer=steer, throttle=throttle, brake=0.0), False


def _snapshot_frame(world, frame_id, simulation_time, ego, lead, control, events, rng, target_speed):
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
            "detections": [_synthetic_detection(lead_snapshot, rng)],
        },
        "planning": {
            "available": True,
            "trajectory_source": "offline_planner",
            "trajectory": _safe_stop_trajectory(world.get_map(), ego, lead),
            "intent": "stop_for_lead_vehicle",
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


def _safe_stop_trajectory(carla_map, ego, lead) -> list[dict[str, Any]]:
    ego_transform = ego.get_transform()
    lead_location = lead.get_location()
    speed = _speed(ego.get_velocity())
    center_distance = ego_transform.location.distance(lead_location)
    half_length_sum = ego.bounding_box.extent.x + lead.bounding_box.extent.x
    safe_travel = max(center_distance - half_length_sum - 1.5, 0.0)
    waypoint = carla_map.get_waypoint(ego_transform.location, project_to_road=True)
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


def _actor_snapshot(actor, *, is_key_actor: bool) -> dict[str, Any]:
    bbox = actor.bounding_box
    return {
        "actor_id": actor.id,
        "type_id": actor.type_id,
        "transform": _transform_dict(actor.get_transform()),
        "velocity": _vector_dict(actor.get_velocity()),
        "acceleration": _vector_dict(actor.get_acceleration()),
        "bounding_box": {"extent": _vector_dict(bbox.extent)},
        "is_key_actor": is_key_actor,
    }


def _synthetic_detection(actor_snapshot: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    transform = json.loads(json.dumps(actor_snapshot["transform"]))
    transform["location"]["x"] += rng.uniform(-0.05, 0.05)
    transform["location"]["y"] += rng.uniform(-0.05, 0.05)
    transform["rotation"]["yaw"] += rng.uniform(-0.2, 0.2)
    return {
        "track_id": f"det_{actor_snapshot['actor_id']}",
        "type": "vehicle",
        "confidence": round(rng.uniform(0.91, 0.96), 4),
        "transform": transform,
        "bounding_box": actor_snapshot["bounding_box"],
        "matched_actor_id": actor_snapshot["actor_id"],
    }


def _vehicle_blueprint(library, preferred_id: str, role_name: str):
    blueprint = library.find(preferred_id)
    if blueprint.has_attribute("role_name"):
        blueprint.set_attribute("role_name", role_name)
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
    desired_yaw = math.degrees(math.atan2(target.y - ego_transform.location.y, target.x - ego_transform.location.x))
    error = (desired_yaw - ego_transform.rotation.yaw + 180.0) % 360.0 - 180.0
    return max(-0.6, min(0.6, error / 45.0))


def _capture_collision(buffer, event) -> None:
    impulse = event.normal_impulse
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
            "attributes": {"marking_types": ",".join(str(item.type) for item in event.crossed_lane_markings)},
        }
    )


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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
