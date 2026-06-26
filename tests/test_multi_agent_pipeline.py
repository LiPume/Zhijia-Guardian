import json
import subprocess
import sys
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.experiments.run_eval import run_multi_agent_eval
from zhijia_guardian.graph import run_diagnosis_graph


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_multi_agent_demo_eval_outputs_trace_and_evidence(tmp_path):
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
    run_dir = run_multi_agent_eval(
        dataset=dataset_dir,
        run_id="pytest_multi_agent_demo",
        output_root=tmp_path / "runs",
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["num_scenarios"] == 6
    assert summary["fault_accuracy"] >= 0.8
    assert summary["evidence_coverage"] == 1.0
    assert summary["hallucination_rate"] == 0.0
    assert (run_dir / "run_report.md").exists()
    assert (run_dir / "artifacts_manifest.json").exists()
    assert (run_dir / "figures" / "confusion_matrix.svg").exists()
    assert (run_dir / "tables" / "errors.csv").exists()
    assert (run_dir / "tables" / "leaderboard.csv").exists()

    diagnosis = json.loads((run_dir / "diagnoses" / "manual_v0_1_000001.json").read_text(encoding="utf-8"))
    assert diagnosis["method"] == "multi_agent_tools"
    assert diagnosis["agent_trace"]
    assert diagnosis["candidate_root_causes"]
    assert (run_dir / "figures" / "manual_v0_1_000001_bev.svg").exists()
    assert (run_dir / "figures" / "manual_v0_1_000001_timeline.svg").exists()
    report_text = (run_dir / "reports" / "manual_v0_1_000001.md").read_text(encoding="utf-8")
    assert "../figures/manual_v0_1_000001_bev.svg" in report_text
    assert "../figures/manual_v0_1_000001_timeline.svg" in report_text
    evidence_ids = {item["evidence_id"] for item in diagnosis["evidence"]}
    for claim in diagnosis["claims"]:
        assert claim["evidence_ids"]
        assert set(claim["evidence_ids"]).issubset(evidence_ids)


def test_multi_agent_graph_observed_view_hides_oracle_and_generation(tmp_path):
    dataset_dir = tmp_path / "manual_json"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_manual_scenarios.py"),
            "--output",
            str(dataset_dir),
            "--count",
            "6",
            "--seed",
            "42",
            "--clean",
        ],
        cwd=REPO_ROOT,
    )
    record = ManualAdapter(dataset_dir).load_scenario("manual_v0_1_000001")
    observed = record.observed_view()
    assert "oracle" not in observed
    assert "generation" not in observed["source"]

    _, diagnosis = run_diagnosis_graph(record)
    serialized = diagnosis.model_dump(mode="json")
    assert "oracle" not in json.dumps(serialized)
