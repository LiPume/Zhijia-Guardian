from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.agents.report_agent import render_markdown_report
from zhijia_guardian.baselines import diagnose_rule_only
from zhijia_guardian.experiments.output_artifacts import write_scenario_artifacts
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.tools.run_metrics import run_all_metrics


def run_unlabeled_diagnosis(
    dataset: str | Path,
    run_id: str,
    *,
    method: str = "multi_agent_tools",
    output_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/outputs/runs",
) -> Path:
    if method not in {"rule_only", "multi_agent_tools"}:
        raise ValueError("unlabeled diagnosis supports rule_only or multi_agent_tools")
    adapter = ManualAdapter(dataset)
    run_dir = Path(output_root) / run_id
    for name in ("metrics", "diagnoses", "reports", "figures", "tables"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)

    rows = []
    for scenario_id in adapter.list_scenarios():
        record = adapter.load_scenario(scenario_id)
        if record.oracle is not None:
            raise ValueError(
                f"{scenario_id} contains oracle; use experiments/run_eval.py for labeled evaluation"
            )
        if method == "multi_agent_tools":
            metrics, diagnosis = run_diagnosis_graph(record)
        else:
            metrics = run_all_metrics(record)
            diagnosis = diagnose_rule_only(record, metrics)
        _write_json(metrics.model_dump(mode="json", exclude_none=True), run_dir / "metrics" / f"{scenario_id}.json")
        _write_json(diagnosis.model_dump(mode="json", exclude_none=True), run_dir / "diagnoses" / f"{scenario_id}.json")
        figure_paths = write_scenario_artifacts(record, diagnosis, run_dir)
        (run_dir / "reports" / f"{scenario_id}.md").write_text(
            render_markdown_report(diagnosis, figure_paths),
            encoding="utf-8",
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "predicted_fault_type": diagnosis.predicted_fault_type,
                "predicted_root_module": diagnosis.predicted_root_module,
                "predicted_fault_start_time": diagnosis.predicted_fault_start_time,
                "confidence": diagnosis.confidence,
            }
        )

    summary = {
        "task": "unlabeled_diagnosis",
        "num_scenarios": len(rows),
        "prediction_counts": dict(Counter(row["predicted_fault_type"] for row in rows)),
        "root_module_counts": dict(Counter(row["predicted_root_module"] for row in rows)),
        "accuracy_metrics_available": False,
        "accuracy_metrics_reason": "No oracle labels are present in this real-world dataset.",
    }
    run_meta = {
        "run_id": run_id,
        "task": "unlabeled_diagnosis",
        "method": method,
        "dataset": str(dataset),
        "git_commit": _git_commit(),
        "created_at": datetime.now().astimezone().isoformat(),
    }
    _write_json(summary, run_dir / "summary.json")
    _write_json(run_meta, run_dir / "run_meta.json")
    _write_index(rows, run_dir / "tables" / "diagnosis_index.csv")
    _write_run_report(run_dir, summary, run_meta, rows)
    _write_json(
        {
            "run_id": run_id,
            "task": "unlabeled_diagnosis",
            "num_scenarios": len(rows),
            "key_files": {
                "run_report": "run_report.md",
                "summary": "summary.json",
                "diagnosis_index": "tables/diagnosis_index.csv",
                "reports": "reports/",
                "diagnoses": "diagnoses/",
            },
        },
        run_dir / "artifacts_manifest.json",
    )
    return run_dir


def _write_index(rows: list[dict], path: Path) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_run_report(run_dir: Path, summary: dict, run_meta: dict, rows: list[dict]) -> None:
    lines = [
        f"# Unlabeled Diagnosis Run {run_meta['run_id']}",
        "",
        "## Boundary",
        "",
        "This run contains no fault/root oracle. Predictions are engineering hypotheses, so accuracy and F1 are unavailable.",
        "",
        "## Metadata",
        "",
        f"- method: `{run_meta['method']}`",
        f"- dataset: `{run_meta['dataset']}`",
        f"- git_commit: `{run_meta['git_commit']}`",
        "",
        "## Prediction Counts",
        "",
    ]
    for label, count in sorted(summary["prediction_counts"].items()):
        lines.append(f"- `{label}`: {count}")
    lines.extend(
        [
            "",
            "## Scenarios",
            "",
            "| Scenario | Predicted fault | Root module | Time | Confidence | Report |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        scenario_id = row["scenario_id"]
        lines.append(
            f"| `{scenario_id}` | `{row['predicted_fault_type']}` | "
            f"`{row['predicted_root_module']}` | {row['predicted_fault_start_time']} | "
            f"{row['confidence']:.3f} | [report](reports/{scenario_id}.md) |"
        )
    (run_dir / "run_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
