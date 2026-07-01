from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from zhijia_guardian.adapters import NuScenesVisionAdapter
from zhijia_guardian.schemas.nuscenes_vision import (
    NuScenesVisionClip,
    NuScenesVisionFrame,
    VisionFrameMetrics,
)
from zhijia_guardian.schemas.scenario import ActorState, Detection, EgoState
from zhijia_guardian.utils.geometry import yaw_from_quaternion_wxyz
from zhijia_guardian.utils.io import dump_scenario_jsonl


DEFAULT_SCENES = ("scene-0103", "scene-0655", "scene-0553", "scene-0796", "scene-1094")
SUPPORTED_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}


def build_nuscenes_vision_benchmark(
    metadata_root: str | Path,
    data_root: str | Path,
    output_root: str | Path,
    weights: str | Path,
    *,
    scene_names: tuple[str, ...] = DEFAULT_SCENES,
    confidence: float = 0.25,
    association_iou: float = 0.3,
    key_actor_min_area: float = 900.0,
    key_actor_max_distance: float = 50.0,
    image_size: int = 640,
    device: str = "0",
    clean: bool = False,
) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("opencv, numpy and official ultralytics are required") from exc

    metadata_root = Path(metadata_root)
    data_root = Path(data_root)
    output_root = Path(output_root)
    weights = Path(weights)
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    clip_root = output_root / "raw" / "clips"
    frame_root = output_root / "media" / "frames"
    video_root = output_root / "media" / "videos"
    canonical_root = output_root / "canonical"
    for path in (clip_root, frame_root, video_root, canonical_root):
        path.mkdir(parents=True, exist_ok=True)

    tables = _load_tables(metadata_root)
    index = _build_index(tables)
    selected_scenes = _select_scenes(tables["scene"], scene_names)
    frame_specs = []
    for scene in selected_scenes:
        frame_specs.extend(_scene_frame_specs(scene, index, data_root))
    missing = [str(spec["image_path"]) for spec in frame_specs if not spec["image_path"].is_file()]
    if missing:
        raise FileNotFoundError(f"missing {len(missing)} CAM_FRONT images; first={missing[0]}")

    model = YOLO(str(weights))
    results_by_sample_data = {}
    for start in range(0, len(frame_specs), 8):
        batch_specs = frame_specs[start : start + 8]
        predictions = model.predict(
            [str(spec["image_path"]) for spec in batch_specs],
            imgsz=image_size,
            conf=confidence,
            device=device,
            classes=[0, 1, 2, 3, 5, 7],
            max_det=100,
            verbose=False,
        )
        results_by_sample_data.update(
            {
                spec["sample_data"]["token"]: result
                for spec, result in zip(batch_specs, predictions)
            }
        )

    manifest_rows = []
    total = defaultdict(int)
    for scene_index, scene in enumerate(selected_scenes, start=1):
        scenario_id = f"nuscenes_real_v0_1_{scene_index:06d}"
        scene_specs = [spec for spec in frame_specs if spec["scene"]["token"] == scene["token"]]
        first_timestamp = scene_specs[0]["sample_data"]["timestamp"] / 1_000_000.0
        clip_frames = []
        rendered_frames = []
        scene_total = defaultdict(int)
        for frame_index, spec in enumerate(scene_specs):
            result = results_by_sample_data[spec["sample_data"]["token"]]
            image = result.orig_img.copy()
            height, width = image.shape[:2]
            ego_pose = index["ego_pose"][spec["sample_data"]["ego_pose_token"]]
            calibrated = index["calibrated_sensor"][spec["sample_data"]["calibrated_sensor_token"]]
            actors = _project_actors(
                spec["sample"]["token"],
                index,
                ego_pose,
                calibrated,
                width,
                height,
                key_actor_min_area,
                key_actor_max_distance,
                np,
            )
            detections, _ = _convert_detections(
                result,
                actors,
                spec["sample"]["token"],
                model.names,
                association_iou,
            )
            matched_actor_ids = {det.matched_gt_id for det in detections if det.matched_gt_id}
            class_correct = sum(
                det.matched_gt_id is not None
                and next(actor.type for actor in actors if actor.actor_id == det.matched_gt_id) == det.type
                for det in detections
            )
            frame_metrics = VisionFrameMetrics(
                visible_gt=len(actors),
                key_actors=sum(actor.is_key_actor for actor in actors),
                detections=len(detections),
                matched=len(matched_actor_ids),
                matched_key_actors=sum(
                    actor.is_key_actor and actor.actor_id in matched_actor_ids for actor in actors
                ),
                class_correct=class_correct,
                false_positives=sum(det.matched_gt_id is None for det in detections),
                missed_key_actors=sum(
                    actor.is_key_actor and actor.actor_id not in matched_actor_ids for actor in actors
                ),
            )
            for key, value in frame_metrics.model_dump().items():
                scene_total[key] += value
                total[key] += value
            timestamp = spec["sample_data"]["timestamp"] / 1_000_000.0 - first_timestamp
            clip_frames.append(
                NuScenesVisionFrame(
                    timestamp=round(timestamp, 6),
                    sample_token=spec["sample"]["token"],
                    sample_data_token=spec["sample_data"]["token"],
                    image_path=str(spec["image_path"]),
                    image_width=width,
                    image_height=height,
                    ego=EgoState(
                        x=ego_pose["translation"][0],
                        y=ego_pose["translation"][1],
                        yaw=yaw_from_quaternion_wxyz(ego_pose["rotation"]),
                    ),
                    actors_gt=actors,
                    detections=detections,
                    metrics=frame_metrics,
                )
            )
            rendered = _render_frame(
                cv2,
                image,
                actors,
                detections,
                scene["name"],
                frame_index,
                frame_metrics,
            )
            rendered_frames.append(rendered)
            target = frame_root / scenario_id / f"{frame_index:04d}.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(target), rendered)

        clip = NuScenesVisionClip(
            scenario_id=scenario_id,
            scene_name=scene["name"],
            scene_token=scene["token"],
            detector_name=f"ultralytics:{weights.stem}",
            detector_weights=str(weights),
            detector_confidence=confidence,
            association_iou_threshold=association_iou,
            frames=clip_frames,
        )
        clip_path = clip_root / f"{scenario_id}.json"
        _write_json(clip.model_dump(mode="json", exclude_none=True), clip_path)
        video_path = video_root / f"{scenario_id}.mp4"
        _write_video(cv2, rendered_frames, video_path, fps=2.0)
        manifest_rows.append(
            {
                "scenario_id": scenario_id,
                "scene_name": scene["name"],
                "num_frames": len(clip_frames),
                "clip_path": str(clip_path.relative_to(output_root)),
                "video_path": str(video_path.relative_to(output_root)),
                "metrics": _summary_metrics(scene_total),
            }
        )

    adapter = NuScenesVisionAdapter(clip_root)
    records = [adapter.load_scenario(scenario_id) for scenario_id in adapter.list_scenarios()]
    dump_scenario_jsonl(records, canonical_root / "scenarios.jsonl")
    manifest = {
        "dataset": "nuscenes_real_cam_front_yolo_v0_1",
        "source_dataset": "nuScenes mini v1.0",
        "oracle_available": False,
        "sensor_channel": "CAM_FRONT",
        "detector": f"ultralytics:{weights.stem}",
        "weights": str(weights),
        "confidence_threshold": confidence,
        "association_iou_threshold": association_iou,
        "num_scenarios": len(manifest_rows),
        "num_frames": len(frame_specs),
        "evaluation_boundary": (
            "nuScenes annotations are projected only for offline association/evaluation; "
            "they are not fault labels and no fault/root accuracy is computed."
        ),
        "aggregate_metrics": _summary_metrics(total),
        "scenarios": manifest_rows,
    }
    _write_json(manifest, output_root / "manifest.json")
    return manifest


def _load_tables(root: Path) -> dict[str, list[dict[str, Any]]]:
    names = (
        "scene",
        "sample",
        "sample_data",
        "ego_pose",
        "sample_annotation",
        "instance",
        "category",
        "calibrated_sensor",
        "sensor",
    )
    return {name: json.loads((root / f"{name}.json").read_text(encoding="utf-8")) for name in names}


def _build_index(tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    index: dict[str, Any] = {
        name: {row["token"]: row for row in rows}
        for name, rows in tables.items()
        if name not in {"sample_annotation", "sample_data"}
    }
    index["sample_annotation"] = defaultdict(list)
    for row in tables["sample_annotation"]:
        index["sample_annotation"][row["sample_token"]].append(row)
    index["sample_data"] = defaultdict(list)
    for row in tables["sample_data"]:
        index["sample_data"][row["sample_token"]].append(row)
    return index


def _select_scenes(rows: list[dict[str, Any]], names: tuple[str, ...]) -> list[dict[str, Any]]:
    by_name = {row["name"]: row for row in rows}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise KeyError(f"unknown nuScenes scenes: {missing}")
    return [by_name[name] for name in names]


def _scene_frame_specs(scene: dict[str, Any], index: dict[str, Any], data_root: Path) -> list[dict[str, Any]]:
    rows = []
    sample_token = scene["first_sample_token"]
    while sample_token:
        sample = index["sample"][sample_token]
        sample_data = _camera_sample_data(sample_token, index)
        rows.append(
            {
                "scene": scene,
                "sample": sample,
                "sample_data": sample_data,
                "image_path": data_root / sample_data["filename"],
            }
        )
        sample_token = sample["next"]
    return rows


def _camera_sample_data(sample_token: str, index: dict[str, Any]) -> dict[str, Any]:
    for row in index["sample_data"][sample_token]:
        calibrated = index["calibrated_sensor"][row["calibrated_sensor_token"]]
        sensor = index["sensor"][calibrated["sensor_token"]]
        if row["is_key_frame"] and sensor["channel"] == "CAM_FRONT":
            return row
    raise KeyError(f"CAM_FRONT key frame missing for {sample_token}")


def _project_actors(
    sample_token: str,
    index: dict[str, Any],
    ego_pose: dict[str, Any],
    calibrated: dict[str, Any],
    image_width: int,
    image_height: int,
    key_min_area: float,
    key_max_distance: float,
    np,
) -> list[ActorState]:
    actors = []
    for annotation in index["sample_annotation"][sample_token]:
        instance = index["instance"][annotation["instance_token"]]
        category = index["category"][instance["category_token"]]["name"]
        normalized = normalize_category(category)
        if normalized is None:
            continue
        bbox = _project_annotation_bbox(
            annotation,
            ego_pose,
            calibrated,
            image_width,
            image_height,
            np,
        )
        if bbox is None:
            continue
        dx = annotation["translation"][0] - ego_pose["translation"][0]
        dy = annotation["translation"][1] - ego_pose["translation"][1]
        distance = math.hypot(dx, dy)
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        size = annotation["size"]
        actors.append(
            ActorState(
                actor_id=annotation["instance_token"],
                type=normalized,
                x=annotation["translation"][0],
                y=annotation["translation"][1],
                yaw=yaw_from_quaternion_wxyz(annotation["rotation"]),
                length=size[1],
                width=size[0],
                height=size[2],
                is_key_actor=area >= key_min_area and distance <= key_max_distance,
                sensor_bbox_xyxy=bbox,
                sensor_channel="CAM_FRONT",
            )
        )
    return actors


def _project_annotation_bbox(annotation, ego_pose, calibrated, width, height, np):
    size = annotation["size"]
    w, length, h = size
    corners = np.array(
        [
            [length / 2, length / 2, length / 2, length / 2, -length / 2, -length / 2, -length / 2, -length / 2],
            [w / 2, -w / 2, -w / 2, w / 2, w / 2, -w / 2, -w / 2, w / 2],
            [h / 2, h / 2, -h / 2, -h / 2, h / 2, h / 2, -h / 2, -h / 2],
        ],
        dtype=float,
    )
    world = _rotation_matrix(annotation["rotation"], np) @ corners
    world += np.asarray(annotation["translation"], dtype=float).reshape(3, 1)
    ego = _rotation_matrix(ego_pose["rotation"], np).T @ (
        world - np.asarray(ego_pose["translation"], dtype=float).reshape(3, 1)
    )
    camera = _rotation_matrix(calibrated["rotation"], np).T @ (
        ego - np.asarray(calibrated["translation"], dtype=float).reshape(3, 1)
    )
    visible = camera[2, :] > 0.1
    if not visible.any():
        return None
    projected = np.asarray(calibrated["camera_intrinsic"], dtype=float) @ camera[:, visible]
    projected[:2, :] /= projected[2:3, :]
    x1 = max(0.0, float(projected[0, :].min()))
    y1 = max(0.0, float(projected[1, :].min()))
    x2 = min(float(width - 1), float(projected[0, :].max()))
    y2 = min(float(height - 1), float(projected[1, :].max()))
    if x2 <= x1 + 2.0 or y2 <= y1 + 2.0:
        return None
    return (round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3))


def _rotation_matrix(quaternion, np):
    w, x, y, z = quaternion
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _convert_detections(result, actors, sample_token, names, iou_threshold):
    raw = []
    if result.boxes is not None:
        for index, (box, class_id, confidence) in enumerate(
            zip(result.boxes.xyxy.tolist(), result.boxes.cls.int().tolist(), result.boxes.conf.tolist())
        ):
            class_name = names[class_id]
            if class_name not in SUPPORTED_CLASSES:
                continue
            raw.append({"index": index, "bbox": tuple(float(value) for value in box), "type": class_name, "confidence": float(confidence)})
    candidates = sorted(
        (
            (_bbox_iou(item["bbox"], actor.sensor_bbox_xyxy), det_index, actor_index)
            for det_index, item in enumerate(raw)
            for actor_index, actor in enumerate(actors)
            if actor.sensor_bbox_xyxy is not None
        ),
        reverse=True,
    )
    assigned_detections = set()
    assigned_actors = set()
    matches = {}
    for iou, det_index, actor_index in candidates:
        if iou < iou_threshold:
            break
        if det_index in assigned_detections or actor_index in assigned_actors:
            continue
        assigned_detections.add(det_index)
        assigned_actors.add(actor_index)
        matches[det_index] = (actor_index, iou)

    detections = []
    for det_index, item in enumerate(raw):
        match = matches.get(det_index)
        if match is None:
            actor = None
            iou = None
            x = None
            y = None
        else:
            actor = actors[match[0]]
            iou = match[1]
            x, y = actor.x, actor.y
        detections.append(
            Detection(
                track_id=(
                    actor.actor_id if actor is not None else f"{sample_token}_det_{item['index']:03d}"
                ),
                type=item["type"],
                confidence=item["confidence"],
                x=x,
                y=y,
                length=actor.length if actor is not None else 0.0,
                width=actor.width if actor is not None else 0.0,
                matched_gt_id=actor.actor_id if actor is not None else None,
                bbox_xyxy=item["bbox"],
                sensor_channel="CAM_FRONT",
                model_class=item["type"],
                association_iou=iou,
            )
        )
    return detections, matches


def _bbox_iou(left, right) -> float:
    if right is None:
        return 0.0
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0.0 else 0.0


def normalize_category(category: str) -> str | None:
    if category.startswith("human.pedestrian"):
        return "person"
    mapping = {
        "vehicle.bicycle": "bicycle",
        "vehicle.car": "car",
        "vehicle.motorcycle": "motorcycle",
        "vehicle.bus.bendy": "bus",
        "vehicle.bus.rigid": "bus",
        "vehicle.truck": "truck",
        "vehicle.trailer": "truck",
        "vehicle.construction": "truck",
    }
    return mapping.get(category)


def _render_frame(cv2, image, actors, detections, scene_name, frame_index, metrics):
    matched_actor_ids = {detection.matched_gt_id for detection in detections if detection.matched_gt_id}
    for actor in actors:
        x1, y1, x2, y2 = map(int, actor.sensor_bbox_xyxy)
        color = (40, 190, 40) if actor.actor_id in matched_actor_ids else (30, 30, 230)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, f"GT {actor.type}", (x1, max(18, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    for detection in detections:
        x1, y1, x2, y2 = map(int, detection.bbox_xyxy)
        color = (220, 160, 20) if detection.matched_gt_id else (20, 160, 230)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)
        cv2.putText(image, f"Y {detection.type} {detection.confidence:.2f}", (x1, min(image.shape[0] - 4, y2 + 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
    banner = f"{scene_name} frame={frame_index:03d} GT={metrics.visible_gt} det={metrics.detections} match={metrics.matched} FP={metrics.false_positives} key_miss={metrics.missed_key_actors}"
    cv2.rectangle(image, (0, 0), (image.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(image, banner, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
    return image


def _write_video(cv2, frames, path: Path, fps: float) -> None:
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"cannot create video {path}")
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()


def _summary_metrics(values: dict[str, int]) -> dict[str, float | int]:
    visible = values["visible_gt"]
    detections = values["detections"]
    matched = values["matched"]
    return {
        **dict(values),
        "annotation_recall": round(matched / visible, 6) if visible else 0.0,
        "detection_precision": round(matched / detections, 6) if detections else 0.0,
        "matched_class_accuracy": (
            round(values["class_correct"] / matched, 6) if matched else 0.0
        ),
        "key_actor_recall": (
            round(values["matched_key_actors"] / values["key_actors"], 6)
            if values["key_actors"]
            else 0.0
        ),
    }


def _write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
