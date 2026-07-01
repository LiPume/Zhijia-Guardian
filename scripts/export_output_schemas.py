#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.failure_sample import FailureSampleRecord


SCHEMAS = {
    "diagnosis_v1.schema.json": DiagnosisRecord,
    "failure_sample_v1.schema.json": FailureSampleRecord,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export versioned diagnosis output JSON Schemas.")
    parser.add_argument("--output-dir", default="docs/contracts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        path = output_dir / filename
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(path)


if __name__ == "__main__":
    main()
