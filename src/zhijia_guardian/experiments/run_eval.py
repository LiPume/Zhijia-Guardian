from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.baselines import diagnose_rule_only
from zhijia_guardian.experiments.eval_metrics import EvalRow, confusion_matrix, evaluate_one, summarize
from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.tools.run_metrics import run_all_metrics


def run_rule_only_eval(
    dataset: str | Path,
    run_id: str,
    output_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/outputs/runs",
    seed: int = 42,
) -> Path:
    adapter = ManualAdapter(dataset)
    run_dir = Path(output_root) / run_id
    metrics_dir = run_dir / "metrics"
    diagnoses_dir = run_dir / "diagnoses"
    reports_dir = run_dir / "reports"
    for path in [metrics_dir, diagnoses_dir, reports_dir]:
        path.mkdir(parents=True, exist_ok=True)

    rows: list[EvalRow] = []
    for scenario_id in adapter.list_scenarios():
        record = adapter.load_scenario(scenario_id)
        metrics = run_all_metrics(record)
        diagnosis = diagnose_rule_only(record, metrics)
        _dump_model(metrics, metrics_dir / f"{scenario_id}.json")
        _dump_model(diagnosis, diagnoses_dir / f"{scenario_id}.json")
        _write_report(diagnosis, reports_dir / f"{scenario_id}.md")
        rows.append(evaluate_one(record, diagnosis))

    _write_eval_csv(rows, run_dir / "eval.csv")
    _write_json(summarize(rows), run_dir / "summary.json")
    _write_json(confusion_matrix(rows), run_dir / "confusion_matrix.json")
    _write_json(
        {
            "run_id": run_id,
            "method": "rule_only",
            "dataset": str(dataset),
            "threshold_config": "configs/thresholds.yaml",
            "llm_config": "configs/llm.yaml",
            "git_commit": _git_commit(),
            "seed": seed,
            "created_at": datetime.now().astimezone().isoformat(),
        },
        run_dir / "run_meta.json",
    )
    return run_dir


def _dump_model(model: MetricsRecord | DiagnosisRecord, path: Path) -> None:
    _write_json(model.model_dump(mode="json", exclude_none=True), path)


def _write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _write_eval_csv(rows: list[EvalRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _write_report(diagnosis: DiagnosisRecord, path: Path) -> None:
    lines = [
        f"# Diagnosis {diagnosis.scenario_id}",
        "",
        f"- predicted_fault_type: `{diagnosis.predicted_fault_type}`",
        f"- predicted_root_module: `{diagnosis.predicted_root_module}`",
        f"- predicted_fault_start_time: `{diagnosis.predicted_fault_start_time}`",
        f"- confidence: `{diagnosis.confidence:.2f}`",
        "",
        "## Evidence",
    ]
    for evidence in diagnosis.evidence:
        lines.append(f"- `{evidence.evidence_id}` `{evidence.metric_name}` {evidence.status}: {evidence.description}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
