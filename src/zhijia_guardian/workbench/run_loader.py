from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/outputs/runs")
DEFAULT_COMPARISON_ROOT = DEFAULT_OUTPUT_ROOT.parent / "comparisons"


@dataclass(frozen=True)
class RunBundle:
    run_dir: Path
    run_id: str
    method: str
    summary: dict[str, Any]
    run_meta: dict[str, Any]
    manifest: dict[str, Any]
    eval_rows: list[dict[str, Any]]
    error_rows: list[dict[str, Any]]
    scenarios: list[str]


def list_runs(output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> list[Path]:
    root = Path(output_root)
    if not root.exists():
        return []
    runs = [path for path in root.iterdir() if path.is_dir() and (path / "summary.json").exists()]
    return sorted(runs, key=lambda path: path.stat().st_mtime, reverse=True)


def list_comparisons(comparison_root: str | Path = DEFAULT_COMPARISON_ROOT) -> list[Path]:
    root = Path(comparison_root)
    if not root.exists():
        return []
    comparisons = [path for path in root.iterdir() if path.is_dir() and (path / "comparison.csv").exists()]
    return sorted(comparisons, key=lambda path: path.stat().st_mtime, reverse=True)


def load_comparison(comparison_dir: str | Path) -> list[dict[str, Any]]:
    return _load_csv(Path(comparison_dir) / "comparison.csv")


def load_run(run_dir: str | Path) -> RunBundle:
    path = Path(run_dir)
    summary = _load_json(path / "summary.json")
    run_meta = _load_json(path / "run_meta.json")
    manifest = _load_json(path / "artifacts_manifest.json") if (path / "artifacts_manifest.json").exists() else {}
    eval_rows = _load_csv(path / "eval.csv")
    errors_path = path / "tables" / "errors.csv"
    error_rows = _load_csv(errors_path) if errors_path.exists() else _filter_errors(eval_rows)
    scenarios = [row["scenario_id"] for row in eval_rows if row.get("scenario_id")]
    return RunBundle(
        run_dir=path,
        run_id=str(run_meta.get("run_id") or path.name),
        method=str(run_meta.get("method") or ""),
        summary=summary,
        run_meta=run_meta,
        manifest=manifest,
        eval_rows=eval_rows,
        error_rows=error_rows,
        scenarios=scenarios,
    )


def load_diagnosis(run_dir: str | Path, scenario_id: str) -> dict[str, Any]:
    return _load_json(Path(run_dir) / "diagnoses" / f"{scenario_id}.json")


def load_metrics(run_dir: str | Path, scenario_id: str) -> dict[str, Any]:
    return _load_json(Path(run_dir) / "metrics" / f"{scenario_id}.json")


def read_report(run_dir: str | Path, scenario_id: str | None = None) -> str:
    path = Path(run_dir) / "run_report.md" if scenario_id is None else Path(run_dir) / "reports" / f"{scenario_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def resolve_figure(run_dir: str | Path, scenario_id: str | None = None, kind: str = "confusion_matrix") -> Path:
    figures = Path(run_dir) / "figures"
    if scenario_id is None:
        return figures / "confusion_matrix.svg"
    if kind not in {"bev", "timeline"}:
        raise ValueError(f"Unsupported scenario figure kind: {kind}")
    return figures / f"{scenario_id}_{kind}.svg"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return [{key: _coerce(value) for key, value in row.items()} for row in csv.DictReader(f)]


def _filter_errors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("fault_correct") is False or row.get("root_correct") is False]


def _coerce(value: str | None) -> Any:
    if value is None or value == "":
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
