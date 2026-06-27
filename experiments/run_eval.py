#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.experiments.run_eval import run_eval  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Zhijia Guardian experiments.")
    parser.add_argument("--method", default="rule_only", choices=["rule_only", "multi_agent_tools", "single_llm"])
    parser.add_argument("--dataset", default="data/sample_scenarios/canonical_demo")
    parser.add_argument("--run-id", default="manual_v0_1_rule_smoke")
    parser.add_argument("--output-root", default="/data5/lzx_data/Zhijia-Guardian/outputs/runs")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", default="configs/thresholds.yaml")
    parser.add_argument("--llm-config", default="configs/llm.yaml")
    parser.add_argument("--enable-llm", action="store_true", help="Acknowledge that the run may call a paid API.")
    parser.add_argument("--limit", type=int, help="Evaluate only the first N scenarios.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = run_eval(
        dataset=args.dataset,
        run_id=args.run_id,
        method=args.method,
        output_root=args.output_root,
        seed=args.seed,
        llm_config_path=args.llm_config,
        enable_llm=args.enable_llm,
        limit=args.limit,
    )
    print(f"Run complete: {run_dir}")


if __name__ == "__main__":
    main()
