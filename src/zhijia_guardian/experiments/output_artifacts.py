from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from zhijia_guardian.experiments.eval_metrics import EvalRow
from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.visualization import render_bev_svg, render_confusion_matrix_svg, render_timeline_svg


def write_scenario_artifacts(
    scenario: ScenarioRecord,
    diagnosis: DiagnosisRecord,
    run_dir: Path,
) -> dict[str, str]:
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    bev_path = figures_dir / f"{scenario.scenario_id}_bev.svg"
    timeline_path = figures_dir / f"{scenario.scenario_id}_timeline.svg"
    bev_path.write_text(render_bev_svg(scenario, diagnosis), encoding="utf-8")
    timeline_path.write_text(render_timeline_svg(scenario, diagnosis), encoding="utf-8")
    return {
        "bev": f"../figures/{bev_path.name}",
        "timeline": f"../figures/{timeline_path.name}",
    }


def write_run_artifacts(
    run_dir: Path,
    rows: list[EvalRow],
    summary: dict[str, float | int],
    confusion: list[dict[str, int | str]],
    run_meta: dict[str, object],
) -> None:
    figures_dir = run_dir / "figures"
    tables_dir = run_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    (figures_dir / "confusion_matrix.svg").write_text(render_confusion_matrix_svg(rows), encoding="utf-8")
    _write_errors_csv(rows, tables_dir / "errors.csv")
    _write_leaderboard_csv(summary, run_meta, tables_dir / "leaderboard.csv")
    _write_run_report(run_dir, rows, summary, confusion, run_meta)
    _write_manifest(run_dir, rows, summary, run_meta)


def _write_errors_csv(rows: list[EvalRow], path: Path) -> None:
    errors = [row for row in rows if not row.fault_correct or not row.root_correct]
    fieldnames = list(asdict(rows[0]).keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in errors:
            writer.writerow(asdict(row))


def _write_leaderboard_csv(summary: dict[str, float | int], run_meta: dict[str, object], path: Path) -> None:
    fieldnames = [
        "run_id",
        "method",
        "dataset",
        "num_scenarios",
        "fault_accuracy",
        "fault_macro_f1",
        "root_top1_accuracy",
        "fault_start_time_mae",
        "evidence_coverage",
        "hallucination_rate",
        "git_commit",
    ]
    row = {
        "run_id": run_meta.get("run_id"),
        "method": run_meta.get("method"),
        "dataset": run_meta.get("dataset"),
        **summary,
        "git_commit": run_meta.get("git_commit"),
    }
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({key: row.get(key) for key in fieldnames})


def _write_run_report(
    run_dir: Path,
    rows: list[EvalRow],
    summary: dict[str, float | int],
    confusion: list[dict[str, int | str]],
    run_meta: dict[str, object],
) -> None:
    errors = [row for row in rows if not row.fault_correct or not row.root_correct]
    lines = [
        f"# Run Report {run_meta.get('run_id')}",
        "",
        "## Metadata",
        "",
        f"- method: `{run_meta.get('method')}`",
        f"- dataset: `{run_meta.get('dataset')}`",
        f"- seed: `{run_meta.get('seed')}`",
        f"- git_commit: `{run_meta.get('git_commit')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in summary.items():
        lines.append(f"| `{key}` | {_fmt(value)} |")
    lines.extend(
        [
            "",
            "## Figures",
            "",
            "![Confusion Matrix](figures/confusion_matrix.svg)",
            "",
            "## Error Cases",
            "",
            "| Scenario | True Fault | Pred Fault | True Root | Pred Root | Report |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in errors[:40]:
        lines.append(
            f"| `{row.scenario_id}` | `{row.true_fault_type}` | `{row.pred_fault_type}` | "
            f"`{row.true_root_module}` | `{row.pred_root_module}` | [report](reports/{row.scenario_id}.md) |"
        )
    if not errors:
        lines.append("| no errors |  |  |  |  |  |")

    lines.extend(["", "## Confusion Counts", "", "| True | Pred | Count |", "| --- | --- | ---: |"])
    for item in confusion:
        lines.append(f"| `{item['true_fault_type']}` | `{item['pred_fault_type']}` | {item['count']} |")
    (run_dir / "run_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_manifest(
    run_dir: Path,
    rows: list[EvalRow],
    summary: dict[str, float | int],
    run_meta: dict[str, object],
) -> None:
    manifest = {
        "run_id": run_meta.get("run_id"),
        "method": run_meta.get("method"),
        "num_scenarios": len(rows),
        "summary": summary,
        "key_files": {
            "run_report": "run_report.md",
            "summary": "summary.json",
            "eval": "eval.csv",
            "errors": "tables/errors.csv",
            "leaderboard": "tables/leaderboard.csv",
            "confusion_matrix": "figures/confusion_matrix.svg",
        },
    }
    with (run_dir / "artifacts_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
