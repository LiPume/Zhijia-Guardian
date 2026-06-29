#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import queue
import random
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np


CASE_FILES = {
    "normal": "03_carla_3d_normal_stop.mp4",
    "control_delay": "04_carla_3d_control_delay.mp4",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture real CARLA RGB videos for two closed-loop cases.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--town", default="Town10HD_Opt")
    parser.add_argument("--output-dir", type=Path, default=Path("/home/lzx/Zhijia-Guardian/demo"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fixed-delta", type=float, default=0.1)
    parser.add_argument("--target-speed", type=float, default=7.0)
    parser.add_argument("--lead-distance", type=float, default=18.0)
    parser.add_argument("--control-delay", type=float, default=0.8)
    parser.add_argument("--max-frames", type=int, default=80)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        import carla
    except ImportError as exc:
        raise SystemExit("Install carla==0.9.15 in the yolo environment first.") from exc

    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world = client.get_world()
    if not world.get_map().name.endswith(f"/{args.town}"):
        raise RuntimeError(
            f"CARLA is running {world.get_map().name}; start a fresh server on {args.town} to avoid hot reload"
        )

    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = args.fixed_delta
    settings.no_rendering_mode = False
    world.apply_settings(settings)
    try:
        spawn_points = _eligible_spawn_points(world.get_map(), args.lead_distance)
        rng = random.Random(args.seed)
        rng.shuffle(spawn_points)
        if not spawn_points:
            raise RuntimeError("no spawn point supports the requested lead distance")
        spawn_transform = spawn_points[0]
        cases = []
        for case_name in ("normal", "control_delay"):
            frames, metadata = _capture_case(carla, world, spawn_transform, case_name, args)
            output_path = args.output_dir / CASE_FILES[case_name]
            _write_video(frames, output_path, fps=1.0 / args.fixed_delta, case_name=case_name)
            metadata["file"] = output_path.name
            cases.append(metadata)
            print(
                f"captured {output_path} frames={len(frames)} collision={metadata['collision']}",
                flush=True,
            )
    finally:
        world.apply_settings(original_settings)

    manifest = {
        "source": "CARLA sensor.camera.rgb",
        "carla_version": client.get_server_version(),
        "map": world.get_map().name,
        "fixed_delta_seconds": args.fixed_delta,
        "target_speed_mps": args.target_speed,
        "lead_distance_m": args.lead_distance,
        "configured_control_delay_s": args.control_delay,
        "cases": cases,
    }
    (args.output_dir / "carla_3d_case_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _capture_case(carla, world, spawn_transform, case_name: str, args: argparse.Namespace):
    actors = []
    sensors = []
    image_queue: queue.Queue = queue.Queue()
    collision_state = {"occurred": False, "frame": None, "other_actor": None}
    try:
        library = world.get_blueprint_library()
        ego_blueprint = _vehicle_blueprint(library, "vehicle.tesla.model3", "hero", "30,90,230")
        lead_blueprint = _vehicle_blueprint(
            library, "vehicle.lincoln.mkz_2020", "scenario", "220,40,40"
        )
        ego = world.try_spawn_actor(ego_blueprint, _raised_transform(carla, spawn_transform))
        if ego is None:
            raise RuntimeError(f"failed to spawn ego for {case_name}")
        actors.append(ego)
        ego_waypoint = world.get_map().get_waypoint(spawn_transform.location, project_to_road=True)
        lead_waypoint = _choose_waypoint(ego_waypoint.next(args.lead_distance))
        lead = world.try_spawn_actor(lead_blueprint, _raised_transform(carla, lead_waypoint.transform))
        if lead is None:
            raise RuntimeError(f"failed to spawn lead actor for {case_name}")
        actors.append(lead)
        lead.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, hand_brake=True))

        camera_blueprint = library.find("sensor.camera.rgb")
        camera_blueprint.set_attribute("image_size_x", str(args.width))
        camera_blueprint.set_attribute("image_size_y", str(args.height))
        camera_blueprint.set_attribute("fov", "100")
        camera_blueprint.set_attribute("sensor_tick", "0.0")
        camera_transform = carla.Transform(
            carla.Location(x=-8.0, y=3.5, z=5.0),
            carla.Rotation(pitch=-18.0, yaw=-18.0),
        )
        camera = world.spawn_actor(
            camera_blueprint,
            camera_transform,
            attach_to=ego,
            attachment_type=carla.AttachmentType.SpringArmGhost,
        )
        camera.listen(image_queue.put)
        sensors.append(camera)

        collision_sensor = world.spawn_actor(
            library.find("sensor.other.collision"), carla.Transform(), attach_to=ego
        )
        collision_sensor.listen(lambda event: _on_collision(collision_state, event))
        sensors.append(collision_sensor)

        for _ in range(6):
            frame_id = world.tick()
            _take_image(image_queue, frame_id, args.width, args.height)
        forward = ego.get_transform().get_forward_vector()
        ego.set_target_velocity(carla.Vector3D(x=forward.x * args.target_speed, y=forward.y * args.target_speed))

        video_frames = []
        risk_started = False
        risk_start_time = None
        brake_start_time = None
        stopped_frames = 0
        collision_followup_frames = 0
        min_ttc = None
        start_elapsed = None
        for _ in range(args.max_frames):
            snapshot_before = world.get_snapshot()
            if start_elapsed is None:
                start_elapsed = snapshot_before.timestamp.elapsed_seconds
            elapsed = snapshot_before.timestamp.elapsed_seconds - start_elapsed
            gap, ttc, speed = _risk_state(ego, lead)
            if ttc is not None:
                min_ttc = ttc if min_ttc is None else min(min_ttc, ttc)
            if not risk_started and ttc is not None and ttc <= 1.25:
                risk_started = True
                risk_start_time = elapsed

            should_brake = risk_started
            fault_active = False
            if case_name == "control_delay" and risk_started and risk_start_time is not None:
                fault_active = elapsed - risk_start_time < args.control_delay
                should_brake = not fault_active
            if should_brake and brake_start_time is None:
                brake_start_time = elapsed

            control = _drive_control(carla, ego, args.target_speed, should_brake)
            ego.apply_control(control)
            frame_id = world.tick()
            image = _take_image(image_queue, frame_id, args.width, args.height)
            snapshot_after = world.get_snapshot()
            current_time = snapshot_after.timestamp.elapsed_seconds - start_elapsed
            gap, ttc, speed = _risk_state(ego, lead)
            annotated = _annotate_frame(
                image,
                case_name=case_name,
                elapsed=current_time,
                speed=speed,
                gap=gap,
                ttc=ttc,
                brake=control.brake,
                fault_active=fault_active,
                collision=collision_state["occurred"],
            )
            video_frames.append(annotated)

            stopped_frames = stopped_frames + 1 if should_brake and speed < 0.2 else 0
            collision_followup_frames = collision_followup_frames + 1 if collision_state["occurred"] else 0
            if stopped_frames >= 10 or collision_followup_frames >= 15:
                break

        return video_frames, {
            "case": case_name,
            "frames": len(video_frames),
            "duration_s": round(len(video_frames) * args.fixed_delta, 3),
            "risk_start_time_s": _round_optional(risk_start_time),
            "brake_start_time_s": _round_optional(brake_start_time),
            "observed_brake_delay_s": _round_optional(
                None
                if risk_start_time is None or brake_start_time is None
                else brake_start_time - risk_start_time
            ),
            "min_ttc_s": _round_optional(min_ttc),
            "collision": collision_state["occurred"],
            "collision_frame": collision_state["frame"],
            "collision_with": collision_state["other_actor"],
        }
    finally:
        for sensor in sensors:
            sensor.stop()
            sensor.destroy()
        for actor in reversed(actors):
            actor.destroy()
        world.tick()


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
    lead_location = lead.get_location()
    forward = transform.get_forward_vector()
    dx = lead_location.x - transform.location.x
    dy = lead_location.y - transform.location.y
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


def _take_image(image_queue: queue.Queue, target_frame: int, width: int, height: int) -> np.ndarray:
    while True:
        try:
            image = image_queue.get(timeout=60.0)
        except queue.Empty as exc:
            raise RuntimeError(
                f"RGB camera produced no frame while waiting for CARLA frame {target_frame}"
            ) from exc
        if image.frame < target_frame:
            continue
        if image.frame > target_frame:
            raise RuntimeError(f"camera skipped frame {target_frame}; received {image.frame}")
        array = np.frombuffer(image.raw_data, dtype=np.uint8).reshape((height, width, 4))
        return array[:, :, :3].copy()


def _annotate_frame(
    image: np.ndarray,
    *,
    case_name: str,
    elapsed: float,
    speed: float,
    gap: float,
    ttc: float | None,
    brake: float,
    fault_active: bool,
    collision: bool,
) -> np.ndarray:
    frame = image.copy()
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], 86), (10, 12, 15), -1)
    cv2.rectangle(overlay, (0, frame.shape[0] - 58), (frame.shape[1], frame.shape[0]), (10, 12, 15), -1)
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
    title = "NORMAL: timely braking" if case_name == "normal" else "FAULT: delayed brake command"
    cv2.putText(frame, title, (24, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (245, 245, 245), 2, cv2.LINE_AA)
    status = "FAULT ACTIVE" if fault_active else "MONITORING"
    if collision:
        status = "COLLISION"
    status_color = (60, 70, 240) if fault_active or collision else (90, 220, 120)
    cv2.putText(frame, status, (24, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.62, status_color, 2, cv2.LINE_AA)
    ttc_text = "n/a" if ttc is None else f"{ttc:.2f}s"
    metrics = (
        f"t={elapsed:4.1f}s   speed={speed * 3.6:4.1f}km/h   gap={gap:4.1f}m   "
        f"TTC={ttc_text}   brake={brake:.2f}"
    )
    cv2.putText(
        frame,
        metrics,
        (24, frame.shape[0] - 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (235, 238, 240),
        1,
        cv2.LINE_AA,
    )
    return frame


def _write_video(frames: list[np.ndarray], output_path: Path, *, fps: float, case_name: str) -> None:
    if not frames:
        raise ValueError(f"no RGB frames captured for {case_name}")
    height, width = frames[0].shape[:2]
    intermediate = output_path.with_name(f".{output_path.stem}.mpeg4.mp4")
    writer = cv2.VideoWriter(
        str(intermediate),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"cannot open video writer: {intermediate}")
    try:
        opening = frames[0].copy()
        shade = opening.copy()
        cv2.rectangle(shade, (130, 185), (width - 130, 355), (8, 10, 12), -1)
        cv2.addWeighted(shade, 0.86, opening, 0.14, 0, opening)
        heading = "CARLA 3D RGB / NORMAL STOP" if case_name == "normal" else "CARLA 3D RGB / CONTROL DELAY"
        cv2.putText(
            opening,
            heading,
            (205, 260),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (250, 250, 250),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            opening,
            "Real sensor.camera.rgb frames",
            (280, 310),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.66,
            (195, 205, 215),
            2,
            cv2.LINE_AA,
        )
        for _ in range(round(fps)):
            writer.write(opening)
        for frame in frames:
            writer.write(frame)
        closing = frames[-1]
        for _ in range(round(fps)):
            writer.write(closing)
    finally:
        writer.release()

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(intermediate),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            check=True,
        )
    finally:
        intermediate.unlink(missing_ok=True)


def _eligible_spawn_points(carla_map, lead_distance: float) -> list[Any]:
    eligible = []
    for transform in carla_map.get_spawn_points():
        waypoint = carla_map.get_waypoint(transform.location, project_to_road=True)
        if waypoint is not None and waypoint.next(lead_distance):
            eligible.append(transform)
    return eligible


def _vehicle_blueprint(library, preferred_id: str, role_name: str, color: str):
    blueprint = library.find(preferred_id)
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
    desired_yaw = math.degrees(math.atan2(target.y - ego_transform.location.y, target.x - ego_transform.location.x))
    error = (desired_yaw - ego_transform.rotation.yaw + 180.0) % 360.0 - 180.0
    return max(-0.6, min(0.6, error / 45.0))


def _speed(vector) -> float:
    return math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)


def _on_collision(state: dict, event) -> None:
    state["occurred"] = True
    state["frame"] = event.frame
    state["other_actor"] = event.other_actor.type_id


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


if __name__ == "__main__":
    main()
