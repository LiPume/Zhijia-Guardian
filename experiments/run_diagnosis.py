#!/usr/bin/env python3
from __future__ import annotations

import argparse

from zhijia_guardian.experiments.run_diagnosis import run_unlabeled_diagnosis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run diagnosis on a dataset without oracle labels.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--method", choices=["rule_only", "multi_agent_tools"], default="multi_agent_tools")
    parser.add_argument("--output-root", default="/data5/lzx_data/Zhijia-Guardian/outputs/runs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = run_unlabeled_diagnosis(
        args.dataset,
        args.run_id,
        method=args.method,
        output_root=args.output_root,
    )
    print(f"Run complete: {run_dir}")


if __name__ == "__main__":
    main()
