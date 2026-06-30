#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EGO_FIELDS = {
    "current_game_time",
    "ego_velocity",
    "ego_acceleration_x",
    "ego_acceleration_y",
    "ego_acceleration_z",
    "ego_x",
    "ego_y",
    "ego_z",
    "ego_roll",
    "ego_pitch",
    "ego_yaw",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert trusted SafeBench planning records.pkl to a versioned JSON export."
    )
    parser.add_argument("--records-pkl", required=True)
    parser.add_argument("--scenario-type-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--safebench-commit", required=True)
    parser.add_argument("--carla-version", required=True)
    parser.add_argument("--fixed-delta-seconds", type=float, default=0.1)
    parser.add_argument(
        "--trusted-input",
        action="store_true",
        help="Required acknowledgement: joblib/pickle can execute code while loading.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.trusted_input:
        raise SystemExit("Refusing to load pickle without --trusted-input")
    if args.fixed_delta_seconds <= 0:
        raise ValueError("--fixed-delta-seconds must be positive")

    try:
        import joblib
    except ImportError as exc:
        raise SystemExit("joblib is required only for this trusted export step") from exc

    records_path = Path(args.records_pkl)
    config_path = Path(args.scenario_type_json)
    raw_records = joblib.load(records_path)
    configs = json.loads(config_path.read_text(encoding="utf-8"))
    config_by_id = {int(item["data_id"]): item for item in configs}

    records = []
    for raw_data_id, sequence in sorted(raw_records.items(), key=lambda item: int(item[0])):
        data_id = int(raw_data_id)
        if data_id not in config_by_id:
            raise KeyError(f"data_id {data_id} is missing from {config_path}")
        config = config_by_id[data_id]
        frames = [_normalize_frame(frame) for frame in sequence]
        records.append(
            {
                "data_id": data_id,
                "scenario_id": int(config["scenario_id"]),
                "route_id": int(config["route_id"]),
                "scenario_folder": str(config["scenario_folder"]),
                "frames": frames,
            }
        )

    payload = {
        "format": "safebench_records_v0_1",
        "scenario_category": "planning",
        "safebench_commit": args.safebench_commit,
        "carla_version": args.carla_version,
        "fixed_delta_seconds": args.fixed_delta_seconds,
        "records": records,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(records)} SafeBench planning records to {output}")


def _normalize_frame(frame: dict[str, Any]) -> dict[str, Any]:
    missing = {"current_game_time", "ego_x", "ego_y"} - frame.keys()
    if missing:
        raise ValueError(f"SafeBench planning frame is missing fields: {sorted(missing)}")
    normalized = {key: _normalize_scalar(frame[key]) for key in EGO_FIELDS if key in frame}
    normalized["criteria"] = {
        key: _normalize_scalar(value) for key, value in frame.items() if key not in EGO_FIELDS
    }
    return normalized


def _normalize_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    enum_name = getattr(value, "name", None)
    if isinstance(enum_name, str):
        return enum_name
    item = getattr(value, "item", None)
    if callable(item):
        scalar = item()
        if scalar is None or isinstance(scalar, (str, int, float, bool)):
            return scalar
    raise TypeError(f"SafeBench planning record contains non-scalar value: {type(value).__name__}")


if __name__ == "__main__":
    main()
