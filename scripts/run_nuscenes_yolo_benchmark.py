#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from zhijia_guardian.benchmarks.nuscenes_vision import (
    DEFAULT_SCENES,
    build_nuscenes_vision_benchmark,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO on real nuScenes CAM_FRONT clips.")
    parser.add_argument(
        "--metadata-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini",
    )
    parser.add_argument(
        "--data-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted",
    )
    parser.add_argument(
        "--output-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1",
    )
    parser.add_argument("--weights", default="/home/lzx/skyline/weights/yolov8n.pt")
    parser.add_argument("--scenes", nargs="+", default=list(DEFAULT_SCENES))
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--association-iou", type=float, default=0.3)
    parser.add_argument("--key-actor-min-area", type=float, default=900.0)
    parser.add_argument("--key-actor-max-distance", type=float, default=50.0)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_nuscenes_vision_benchmark(
        args.metadata_root,
        args.data_root,
        args.output_root,
        args.weights,
        scene_names=tuple(args.scenes),
        confidence=args.confidence,
        association_iou=args.association_iou,
        key_actor_min_area=args.key_actor_min_area,
        key_actor_max_distance=args.key_actor_max_distance,
        image_size=args.image_size,
        device=args.device,
        clean=args.clean,
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "scenarios"}, indent=2))


if __name__ == "__main__":
    main()
