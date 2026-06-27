from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


METRICS = [
    "fault_accuracy",
    "fault_macro_f1",
    "root_top1_accuracy",
    "fault_start_time_mae",
    "evidence_coverage",
    "evidence_correctness",
    "hallucination_rate",
]


def compare_runs(run_dirs: list[str | Path], output_dir: str | Path) -> Path:
    if len(run_dirs) < 2:
        raise ValueError("At least two run directories are required")

    records = [_load_run(Path(path)) for path in run_dirs]
    methods = [record["method"] for record in records]
    if len(set(methods)) != len(methods):
        raise ValueError(f"Run methods must be unique: {methods}")

    reference_ids = records[0].pop("scenario_ids")
    for record in records[1:]:
        scenario_ids = record.pop("scenario_ids")
        if scenario_ids != reference_ids:
            raise ValueError(f"Scenario set mismatch for method {record['method']}")

    records[0].pop("scenario_ids", None)
    records.sort(key=lambda item: (-float(item["fault_macro_f1"]), item["method"]))
    for rank, record in enumerate(records, start=1):
        record["macro_f1_rank"] = rank

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    payload = {
        "num_methods": len(records),
        "num_scenarios": len(reference_ids),
        "scenario_sets_match": True,
        "ranking_metric": "fault_macro_f1",
        "comparison_git_commit": _git_commit(),
        "created_at": datetime.now().astimezone().isoformat(),
        "runs": records,
    }
    _write_json(payload, destination / "comparison.json")
    _write_csv(records, destination / "comparison.csv")
    (destination / "comparison.md").write_text(_render_markdown(payload), encoding="utf-8")
    return destination


def _load_run(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    meta_path = run_dir / "run_meta.json"
    eval_path = run_dir / "eval.csv"
    for path in [summary_path, meta_path, eval_path]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing run artifact: {path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    with eval_path.open(encoding="utf-8", newline="") as handle:
        scenario_ids = {row["scenario_id"] for row in csv.DictReader(handle)}
    if len(scenario_ids) != int(summary["num_scenarios"]):
        raise ValueError(f"Scenario count mismatch inside {run_dir}")

    llm = meta.get("llm", {})
    return {
        "run_id": meta["run_id"],
        "method": meta["method"],
        "model": llm.get("model"),
        "provider": llm.get("provider"),
        "dataset": meta["dataset"],
        "seed": meta["seed"],
        "git_commit": meta["git_commit"],
        **{metric: summary[metric] for metric in METRICS},
        "scenario_ids": scenario_ids,
    }


def _write_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(records: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "macro_f1_rank",
        "method",
        "provider",
        "model",
        *METRICS,
        "run_id",
        "dataset",
        "seed",
        "git_commit",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Run Comparison",
        "",
        f"- Scenarios: {payload['num_scenarios']}",
        f"- Scenario sets match: {payload['scenario_sets_match']}",
        f"- Ranking metric: `{payload['ranking_metric']}`",
        f"- Comparison commit: `{payload['comparison_git_commit']}`",
        "",
        "| Rank | Method | Model | Accuracy | Macro-F1 | Root Top-1 | Time MAE | Evidence Correctness | Hallucination Rate |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for record in payload["runs"]:
        model = record["model"] or "-"
        lines.append(
            f"| {record['macro_f1_rank']} | `{record['method']}` | `{model}` | "
            f"{record['fault_accuracy']:.4f} | {record['fault_macro_f1']:.4f} | "
            f"{record['root_top1_accuracy']:.4f} | {record['fault_start_time_mae']:.4f} | "
            f"{record['evidence_correctness']:.4f} | {record['hallucination_rate']:.4f} |"
        )
    lines.extend(["", "## Runs", ""])
    for record in payload["runs"]:
        lines.append(
            f"- `{record['method']}`: `{record['run_id']}` at commit `{record['git_commit']}`"
        )
    return "\n".join(lines) + "\n"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
