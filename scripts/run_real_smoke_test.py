#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.adapters import NuPlanAdapter, NuScenesAdapter
from zhijia_guardian.tools.coverage import field_coverage
from zhijia_guardian.utils.io import dump_scenario_record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export one nuScenes and one nuPlan smoke-test ScenarioRecord.")
    parser.add_argument(
        "--output-dir",
        default="data/sample_scenarios/real_smoke_test",
        help="Output directory for ScenarioRecord JSON and coverage report.",
    )
    parser.add_argument(
        "--nuscenes-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini",
    )
    parser.add_argument(
        "--nuplan-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini",
    )
    return parser.parse_args()


def assert_no_oracle_in_observed(record) -> None:
    observed = record.observed_view()
    if "oracle" in observed:
        raise AssertionError(f"oracle leaked into observed view for {record.scenario_id}")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    adapters = [
        ("nuscenes", NuScenesAdapter(args.nuscenes_root)),
        ("nuplan", NuPlanAdapter(args.nuplan_root)),
    ]

    coverage_rows = []
    for name, adapter in adapters:
        scenario_ids = adapter.list_scenarios()
        if not scenario_ids:
            raise RuntimeError(f"{name} adapter did not list any scenarios")
        record = adapter.load_scenario(scenario_ids[0])
        assert_no_oracle_in_observed(record)
        dump_scenario_record(record, output_dir / f"{record.scenario_id}.json")
        coverage_rows.append(field_coverage(record))

    with (output_dir / "field_coverage.json").open("w", encoding="utf-8") as f:
        json.dump(coverage_rows, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Exported {len(coverage_rows)} smoke scenarios to {output_dir}")
    for row in coverage_rows:
        print(
            f"- {row['scenario_id']} ({row['dataset']}): "
            f"frames={row['num_frames']} skipped={','.join(row['skipped_agents']) or 'none'}"
        )


if __name__ == "__main__":
    main()
