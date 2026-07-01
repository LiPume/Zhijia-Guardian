#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from zhijia_guardian.benchmarks.carla_weather import record_carla_weather_benchmark


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record CARLA extreme-weather diagnosis scenarios.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--town", default="Town10HD_Opt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fixed-delta", type=float, default=0.1)
    parser.add_argument("--max-frames", type=int, default=80)
    parser.add_argument("--lead-distance", type=float, default=18.0)
    parser.add_argument("--target-speed", type=float, default=7.0)
    parser.add_argument("--control-delay", type=float, default=0.8)
    parser.add_argument("--planning-fault-start", type=float, default=0.5)
    parser.add_argument("--perception-fault-start", type=float, default=0.5)
    parser.add_argument("--no-rendering", action="store_true")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = record_carla_weather_benchmark(
        args.output_root,
        host=args.host,
        port=args.port,
        town=args.town,
        seed=args.seed,
        fixed_delta_seconds=args.fixed_delta,
        max_frames=args.max_frames,
        lead_distance=args.lead_distance,
        target_speed=args.target_speed,
        control_delay=args.control_delay,
        planning_fault_start=args.planning_fault_start,
        perception_fault_start=args.perception_fault_start,
        no_rendering=args.no_rendering,
        clean=args.clean,
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "scenarios"}, indent=2))


if __name__ == "__main__":
    main()
