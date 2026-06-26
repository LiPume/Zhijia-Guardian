import json
import subprocess
import sys
from pathlib import Path

from zhijia_guardian.workbench import list_runs, load_diagnosis, load_run, read_report, resolve_figure


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_workbench_loads_run_artifacts(tmp_path):
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
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "experiments" / "run_eval.py"),
            "--method",
            "multi_agent_tools",
            "--dataset",
            str(dataset_dir),
            "--run-id",
            "pytest_workbench",
            "--output-root",
            str(tmp_path / "runs"),
        ],
        cwd=REPO_ROOT,
    )

    runs = list_runs(tmp_path / "runs")
    assert [path.name for path in runs] == ["pytest_workbench"]

    bundle = load_run(runs[0])
    assert bundle.run_id == "pytest_workbench"
    assert bundle.method == "multi_agent_tools"
    assert bundle.summary["num_scenarios"] == 6
    assert len(bundle.scenarios) == 6

    scenario_id = bundle.scenarios[0]
    diagnosis = load_diagnosis(bundle.run_dir, scenario_id)
    assert diagnosis["scenario_id"] == scenario_id
    assert read_report(bundle.run_dir, scenario_id).startswith("# Diagnosis")
    assert resolve_figure(bundle.run_dir, scenario_id, "bev").exists()
    assert resolve_figure(bundle.run_dir, scenario_id, "timeline").exists()
    assert resolve_figure(bundle.run_dir).exists()

    manifest = json.loads((bundle.run_dir / "artifacts_manifest.json").read_text(encoding="utf-8"))
    assert manifest["key_files"]["run_report"] == "run_report.md"
