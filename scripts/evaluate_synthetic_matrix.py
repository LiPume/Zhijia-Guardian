#!/usr/bin/env python3
"""Evaluate adaptive routing against a fixed-pipeline control on four tiny synthetic cases."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from zhijia_guardian.evaluation import evaluate_synthetic_fault_matrix, summarize_matrix


def main() -> None:
  parser = argparse.ArgumentParser()
  parser.add_argument("--output", type=Path, default=None, help="Defaults to $ZHIJIA_DATA_ROOT/outputs/synthetic-matrix-evaluation.json")
  args = parser.parse_args()
  output = args.output or Path(os.environ.get("ZHIJIA_DATA_ROOT", "data")) / "outputs" / "synthetic-matrix-evaluation.json"
  payload = summarize_matrix(evaluate_synthetic_fault_matrix())
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(payload["summary"], indent=2))
  print(f"evaluation artifact: {output}")


if __name__ == "__main__":
  main()
