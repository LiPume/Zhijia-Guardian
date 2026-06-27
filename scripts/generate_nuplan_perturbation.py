#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.adapters import NuPlanAdapter  # noqa: E402
from zhijia_guardian.benchmarks import build_nuplan_perturbation_records  # noqa: E402
from zhijia_guardian.tools.planning_eval import evaluate_planning  # noqa: E402
from zhijia_guardian.utils.io import dump_scenario_record  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate paired planning perturbations on real nuPlan scenes.")
    parser.add_argument(
        "--nuplan-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini",
    )
    parser.add_argument(
        "--output",
        default=(
            "/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini/derived/"
            "planning_perturbation_v0_1"
        ),
    )
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-displacement", type=float, default=8.0)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    if args.clean and output.exists():
        shutil.rmtree(output)
    records_dir = output / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    adapter = NuPlanAdapter(args.nuplan_root)
    records = build_nuplan_perturbation_records(
        adapter,
        pair_count=args.pairs,
        seed=args.seed,
        max_displacement=args.max_displacement,
    )
    labels = Counter()
    rows = []
    for record in records:
        dump_scenario_record(record, records_dir / f"{record.scenario_id}.json")
        oracle = record.load_oracle_for_eval()
        label = oracle.fault_type if oracle and oracle.fault_type else "normal"
        labels[label] += 1
        planning = evaluate_planning(record)
        rows.append(
            {
                "scenario_id": record.scenario_id,
                "parent_scenario_id": record.source.generation["parent_scenario_id"],
                "fault_type": label,
                "planning_collision_count": planning.trajectory_collision_count,
                "min_trajectory_margin": planning.min_trajectory_margin,
            }
        )

    manifest = {
        "benchmark": "nuplan_planning_perturbation_v0_1",
        "seed": args.seed,
        "num_pairs": args.pairs,
        "num_records": len(records),
        "label_distribution": dict(labels),
        "records": rows,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(records)} nuPlan perturbation records under {output}")
    print(f"Distribution: {dict(labels)}")


if __name__ == "__main__":
    main()
