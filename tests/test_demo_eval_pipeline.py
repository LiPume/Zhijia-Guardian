import json
import subprocess
import sys
from pathlib import Path

from zhijia_guardian.experiments.run_eval import run_rule_only_eval


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_demo_generation_and_rule_eval(tmp_path):
    dataset_dir = tmp_path / "canonical_demo"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_canonical_demo.py"),
            "--output-dir",
            str(dataset_dir),
        ],
        cwd=REPO_ROOT,
    )
    assert len(list(dataset_dir.rglob("*.json"))) == 6

    run_dir = run_rule_only_eval(
        dataset=dataset_dir,
        run_id="pytest_rule_demo",
        output_root=tmp_path / "runs",
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["num_scenarios"] == 6
    assert summary["fault_accuracy"] >= 0.8
    assert (run_dir / "eval.csv").exists()
    assert len(list((run_dir / "metrics").glob("*.json"))) == 6
    assert len(list((run_dir / "diagnoses").glob("*.json"))) == 6
