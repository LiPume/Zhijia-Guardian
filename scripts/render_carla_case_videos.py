#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

from zhijia_guardian.adapters import CarlaAdapter
from zhijia_guardian.schemas.scenario import Detection, FrameRecord, ScenarioRecord


DEFAULT_DATASET = Path("/data5/lzx_data/Zhijia-Guardian/datasets/carla/fault_benchmark_v0_1")
DEFAULT_OUTPUT = Path("/data5/lzx_data/Zhijia-Guardian/outputs/case_videos/carla_v0_1")
CASE_NAMES = {
    "perception_miss": "01_perception_miss_comparison.mp4",
    "planning_collision_risk": "02_planning_collision_risk_comparison.mp4",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render paired CARLA diagnosis videos from canonical logs.")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--parent-group", default="carla_parent_0001")
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--frame-repeat", type=int, default=2)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=sorted(CASE_NAMES),
        default=list(CASE_NAMES),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.fps <= 0 or args.frame_repeat <= 0:
        raise ValueError("fps and frame-repeat must be positive")
    log_dir = args.dataset_root / "raw" / "logs"
    label_dir = args.dataset_root / "raw" / "labels"
    manifest_path = label_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [row for row in manifest["scenarios"] if row["parent_group"] == args.parent_group]
    scenario_by_variant = {row["variant"]: row["scenario_id"] for row in rows}
    if "normal" not in scenario_by_variant:
        raise KeyError(f"normal pair is missing for {args.parent_group}")

    adapter = CarlaAdapter(log_dir, label_dir)
    normal = adapter.load_scenario(scenario_by_variant["normal"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    video_rows = []
    for variant in args.variants:
        if variant not in scenario_by_variant:
            raise KeyError(f"{variant} is missing for {args.parent_group}")
        fault = adapter.load_scenario(scenario_by_variant[variant])
        output_path = args.output_dir / CASE_NAMES[variant]
        num_frames = render_pair_video(
            normal,
            fault,
            output_path,
            fps=args.fps,
            frame_repeat=args.frame_repeat,
        )
        video_rows.append(
            {
                "file": output_path.name,
                "normal_scenario_id": normal.scenario_id,
                "fault_scenario_id": fault.scenario_id,
                "fault_type": variant,
                "video_frames": num_frames,
                "fps": args.fps,
            }
        )
        print(f"rendered {output_path} ({num_frames} frames)", flush=True)

    index = {
        "dataset": manifest["dataset"],
        "parent_group": args.parent_group,
        "visualization": "paired ego-centric BEV from real CARLA state logs",
        "legend": {
            "simulation_gt": "red",
            "perception_detection": "green",
            "planned_trajectory": "yellow",
            "ego": "blue",
        },
        "videos": video_rows,
    }
    (args.output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_pair_video(
    normal: ScenarioRecord,
    fault: ScenarioRecord,
    output_path: Path,
    *,
    fps: float = 10.0,
    frame_repeat: int = 2,
) -> int:
    if len(normal.frames) != len(fault.frames):
        raise ValueError("paired scenarios must have equal frame counts")
    width, height = 1280, 720
    intermediate_path = output_path.with_name(f".{output_path.stem}.mpeg4.mp4")
    writer = cv2.VideoWriter(
        str(intermediate_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"cannot open video writer: {output_path}")

    fault_type = fault.oracle.fault_type if fault.oracle else "fault"
    fault_start = fault.oracle.fault_start_time if fault.oracle else None
    total_written = 0
    try:
        opening = _compose_frame(normal.frames[0], fault.frames[0], fault_type, fault_start, intro=True)
        for _ in range(round(fps)):
            writer.write(opening)
            total_written += 1
        for normal_frame, fault_frame in zip(normal.frames, fault.frames):
            canvas = _compose_frame(normal_frame, fault_frame, fault_type, fault_start)
            for _ in range(frame_repeat):
                writer.write(canvas)
                total_written += 1
        closing = _compose_frame(normal.frames[-1], fault.frames[-1], fault_type, fault_start)
        cv2.putText(
            closing,
            "CASE COMPLETE",
            (510, 690),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (235, 235, 235),
            2,
            cv2.LINE_AA,
        )
        for _ in range(round(fps)):
            writer.write(closing)
            total_written += 1
    finally:
        writer.release()
    _transcode_h264(intermediate_path, output_path)
    return total_written


def _compose_frame(
    normal_frame: FrameRecord,
    fault_frame: FrameRecord,
    fault_type: str,
    fault_start: float | None,
    *,
    intro: bool = False,
) -> np.ndarray:
    canvas = np.full((720, 1280, 3), (23, 25, 28), dtype=np.uint8)
    active = fault_start is not None and fault_frame.timestamp + 1e-6 >= fault_start
    title = f"CARLA paired diagnosis case: {fault_type}"
    cv2.putText(canvas, title, (28, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (245, 245, 245), 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        f"t={fault_frame.timestamp:4.1f}s",
        (1120, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (205, 210, 215),
        2,
        cv2.LINE_AA,
    )

    left = _draw_panel(normal_frame, "NORMAL REPLAY", fault_active=False)
    right_title = f"FAULT REPLAY: {fault_type}"
    right = _draw_panel(fault_frame, right_title, fault_active=active)
    canvas[58:658, 0:640] = left
    canvas[58:658, 640:1280] = right
    cv2.line(canvas, (640, 58), (640, 658), (75, 78, 82), 2)

    state = "FAULT ACTIVE" if active else "BEFORE INJECTION"
    state_color = (65, 80, 235) if active else (170, 175, 180)
    cv2.putText(canvas, state, (842, 696), cv2.FONT_HERSHEY_SIMPLEX, 0.72, state_color, 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        "Red: simulation GT   Green: perception   Yellow: planned path   Blue: ego",
        (22, 696),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.49,
        (190, 195, 200),
        1,
        cv2.LINE_AA,
    )
    if intro:
        overlay = canvas.copy()
        cv2.rectangle(overlay, (315, 275), (965, 435), (12, 14, 17), -1)
        cv2.addWeighted(overlay, 0.88, canvas, 0.12, 0, canvas)
        cv2.putText(
            canvas,
            "SAME CARLA SCENE / DIFFERENT MODULE OUTPUT",
            (378, 335),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.67,
            (245, 245, 245),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "Left: normal   Right: injected fault",
            (462, 385),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (195, 205, 215),
            2,
            cv2.LINE_AA,
        )
    return canvas


def _draw_panel(frame: FrameRecord, title: str, *, fault_active: bool) -> np.ndarray:
    panel = np.full((600, 640, 3), (31, 34, 38), dtype=np.uint8)
    cv2.putText(panel, title, (18, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 238, 240), 2, cv2.LINE_AA)
    if fault_active:
        cv2.circle(panel, (613, 20), 7, (65, 75, 235), -1, cv2.LINE_AA)

    _draw_grid(panel)
    ego = frame.ego
    for actor in frame.actors_gt:
        polygon = _box_polygon(actor.x, actor.y, actor.yaw, actor.length, actor.width, ego)
        _fill_polygon(panel, polygon, (50, 55, 155), alpha=0.45)
        cv2.polylines(panel, [polygon], True, (70, 80, 235), 2, cv2.LINE_AA)
        _label_at(panel, polygon, f"GT {actor.actor_id}", (105, 115, 245))

    for detection in frame.perception.detections:
        polygon = _detection_polygon(detection, ego)
        cv2.polylines(panel, [polygon], True, (80, 220, 110), 2, cv2.LINE_AA)
        _label_at(panel, polygon, f"DET {detection.confidence:.2f}", (100, 235, 125), offset=16)

    trajectory_pixels = [_world_to_pixel(point.x, point.y, ego) for point in frame.planning.trajectory]
    if len(trajectory_pixels) >= 2:
        points = np.array(trajectory_pixels, dtype=np.int32)
        cv2.polylines(panel, [points], False, (30, 205, 245), 3, cv2.LINE_AA)
        for point in trajectory_pixels:
            cv2.circle(panel, point, 4, (30, 205, 245), -1, cv2.LINE_AA)

    ego_polygon = _box_polygon(ego.x, ego.y, ego.yaw, ego.length, ego.width, ego)
    _fill_polygon(panel, ego_polygon, (195, 125, 25), alpha=0.75)
    cv2.polylines(panel, [ego_polygon], True, (255, 185, 55), 2, cv2.LINE_AA)
    _label_at(panel, ego_polygon, "EGO", (255, 200, 90), offset=17)

    ttc = _frame_ttc(frame)
    ttc_text = "n/a" if ttc is None else f"{ttc:.2f}s"
    control = frame.control
    detection_state = "yes" if _key_actor_detected(frame) else "NO"
    cv2.rectangle(panel, (16, 535), (624, 588), (21, 23, 26), -1)
    cv2.putText(
        panel,
        f"TTC {ttc_text}   brake {control.brake or 0.0:.2f}   throttle {control.throttle or 0.0:.2f}",
        (28, 558),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.53,
        (220, 223, 225),
        1,
        cv2.LINE_AA,
    )
    detection_color = (80, 220, 110) if detection_state == "yes" else (75, 80, 240)
    cv2.putText(
        panel,
        f"key actor detected: {detection_state}",
        (28, 580),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.49,
        detection_color,
        1,
        cv2.LINE_AA,
    )
    return panel


def _draw_grid(panel: np.ndarray) -> None:
    for lateral in (-15, -10, -5, 0, 5, 10, 15):
        x, _ = _local_to_pixel(0.0, float(lateral))
        cv2.line(panel, (x, 42), (x, 524), (49, 52, 57), 1)
    for longitudinal in (-8, 0, 10, 20, 30):
        _, y = _local_to_pixel(float(longitudinal), 0.0)
        cv2.line(panel, (20, y), (620, y), (49, 52, 57), 1)
        cv2.putText(
            panel,
            f"{longitudinal}m",
            (22, max(54, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (115, 120, 125),
            1,
            cv2.LINE_AA,
        )
    for lateral in (-1.8, 1.8):
        x, _ = _local_to_pixel(0.0, lateral)
        cv2.line(panel, (x, 42), (x, 524), (105, 108, 112), 1, cv2.LINE_AA)


def _box_polygon(x: float, y: float, yaw: float, length: float, width: float, ego) -> np.ndarray:
    half_length = max(length, 0.2) / 2.0
    half_width = max(width, 0.2) / 2.0
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    pixels = []
    for forward, lateral in (
        (half_length, half_width),
        (half_length, -half_width),
        (-half_length, -half_width),
        (-half_length, half_width),
    ):
        world_x = x + forward * cos_yaw - lateral * sin_yaw
        world_y = y + forward * sin_yaw + lateral * cos_yaw
        pixels.append(_world_to_pixel(world_x, world_y, ego))
    return np.array(pixels, dtype=np.int32)


def _detection_polygon(detection: Detection, ego) -> np.ndarray:
    return _box_polygon(
        detection.x,
        detection.y,
        detection.yaw,
        detection.length,
        detection.width,
        ego,
    )


def _world_to_pixel(x: float, y: float, ego) -> tuple[int, int]:
    dx, dy = x - ego.x, y - ego.y
    cos_yaw, sin_yaw = math.cos(ego.yaw), math.sin(ego.yaw)
    longitudinal = dx * cos_yaw + dy * sin_yaw
    lateral = -dx * sin_yaw + dy * cos_yaw
    return _local_to_pixel(longitudinal, lateral)


def _local_to_pixel(longitudinal: float, lateral: float) -> tuple[int, int]:
    scale = 12.0
    return round(320 - lateral * scale), round(428 - longitudinal * scale)


def _fill_polygon(image: np.ndarray, polygon: np.ndarray, color: tuple[int, int, int], alpha: float) -> None:
    overlay = image.copy()
    cv2.fillPoly(overlay, [polygon], color, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, image, 1.0 - alpha, 0, image)


def _label_at(
    image: np.ndarray,
    polygon: np.ndarray,
    text: str,
    color: tuple[int, int, int],
    *,
    offset: int = 4,
) -> None:
    x = int(np.min(polygon[:, 0]))
    y = int(np.min(polygon[:, 1])) - offset
    cv2.putText(
        image,
        text,
        (max(4, x), max(48, y)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        color,
        1,
        cv2.LINE_AA,
    )


def _key_actor_detected(frame: FrameRecord) -> bool:
    key_ids = {actor.actor_id for actor in frame.actors_gt if actor.is_key_actor}
    return any(detection.matched_gt_id in key_ids for detection in frame.perception.detections)


def _frame_ttc(frame: FrameRecord) -> float | None:
    ego = frame.ego
    cos_yaw, sin_yaw = math.cos(ego.yaw), math.sin(ego.yaw)
    best = None
    for actor in frame.actors_gt:
        dx, dy = actor.x - ego.x, actor.y - ego.y
        longitudinal = dx * cos_yaw + dy * sin_yaw
        lateral = -dx * sin_yaw + dy * cos_yaw
        ego_speed = ego.vx * cos_yaw + ego.vy * sin_yaw
        actor_speed = actor.vx * cos_yaw + actor.vy * sin_yaw
        closing_speed = ego_speed - actor_speed
        if longitudinal <= 0.0 or abs(lateral) > 3.0 or closing_speed <= 0.1:
            continue
        ttc = longitudinal / closing_speed
        best = ttc if best is None else min(best, ttc)
    return best


def _transcode_h264(intermediate_path: Path, output_path: Path) -> None:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(intermediate_path),
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
        intermediate_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
