#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from zhijia_guardian.benchmarks.carla_fault_injection import (
    build_carla_fault_benchmark,
    build_carla_fault_benchmark_v0_2,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build paired CARLA fault-injection scenarios from base logs.")
    parser.add_argument("--base-log-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--version", choices=["v0_1", "v0_2"], default="v0_1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.version == "v0_2":
        manifest = build_carla_fault_benchmark_v0_2(
            args.base_log_dir,
            args.output_root,
            seed=args.seed,
            clean=args.clean,
        )
    else:
        manifest = build_carla_fault_benchmark(args.base_log_dir, args.output_root, clean=args.clean)
    print(json.dumps({key: value for key, value in manifest.items() if key != "scenarios"}, indent=2))


if __name__ == "__main__":
    main()
