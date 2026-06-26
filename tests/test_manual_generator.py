import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manual_generator_count_metadata_and_no_filename_leak(tmp_path):
    output = tmp_path / "manual_json" / "v0_1"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_manual_scenarios.py"),
            "--seed",
            "7",
            "--count",
            "12",
            "--output",
            str(output),
            "--clean",
        ],
        cwd=REPO_ROOT,
    )
    files = sorted(output.rglob("*.json"))
    assert len(files) == 12
    forbidden = [
        "perception_miss",
        "perception_false_positive",
        "perception_confidence_drop",
        "planning_collision_risk",
        "control_delay",
    ]
    for path in files:
        assert not any(label in path.name for label in forbidden)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["source"]["generation"]["generation_seed"] == 7
        assert data["oracle"]["visible_to_diagnosis"] is False
        assert "fault_type" not in data["scenario_id"]
