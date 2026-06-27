#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.experiments.compare_runs import compare_runs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare reproducible Zhijia Guardian run packages.")
    parser.add_argument("run_dirs", nargs="+", help="Two or more run directories.")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = compare_runs(args.run_dirs, args.output_dir)
    print(f"Comparison complete: {output_dir}")


if __name__ == "__main__":
    main()
