from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.agents.report_agent import render_markdown_report
from zhijia_guardian.baselines import (
    LLMConfig,
    SingleLLMClient,
    create_single_llm_client,
    diagnose_rule_only,
    diagnose_single_llm,
    load_llm_config,
)
from zhijia_guardian.experiments.eval_metrics import EvalRow, confusion_matrix, evaluate_one, summarize
from zhijia_guardian.experiments.failure_sample_builder import (
    build_failure_sample,
    write_failure_sample_package,
)
from zhijia_guardian.experiments.output_artifacts import write_run_artifacts, write_scenario_artifacts
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.failure_sample import FailureSampleRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.run_metrics import run_all_metrics


def run_rule_only_eval(
    dataset: str | Path,
    run_id: str,
    output_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/outputs/runs",
    seed: int = 42,
) -> Path:
    return run_eval(dataset=dataset, run_id=run_id, method="rule_only", output_root=output_root, seed=seed)


def run_multi_agent_eval(
    dataset: str | Path,
    run_id: str,
    output_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/outputs/runs",
    seed: int = 42,
) -> Path:
    return run_eval(dataset=dataset, run_id=run_id, method="multi_agent_tools", output_root=output_root, seed=seed)


def run_single_llm_eval(
    dataset: str | Path,
    run_id: str,
    output_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/outputs/runs",
    seed: int = 42,
    llm_config_path: str | Path = "configs/llm.yaml",
    enable_llm: bool = False,
    llm_client: SingleLLMClient | None = None,
    limit: int | None = None,
    resume: bool = False,
) -> Path:
    return run_eval(
        dataset=dataset,
        run_id=run_id,
        method="single_llm",
        output_root=output_root,
        seed=seed,
        llm_config_path=llm_config_path,
        enable_llm=enable_llm,
        llm_client=llm_client,
        limit=limit,
        resume=resume,
    )


def run_eval(
    dataset: str | Path,
    run_id: str,
    method: str,
    output_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/outputs/runs",
    seed: int = 42,
    llm_config_path: str | Path = "configs/llm.yaml",
    enable_llm: bool = False,
    llm_client: SingleLLMClient | None = None,
    limit: int | None = None,
    resume: bool = False,
) -> Path:
    if method not in {"rule_only", "multi_agent_tools", "single_llm"}:
        raise ValueError(f"Unsupported method: {method}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")

    active_llm_config: LLMConfig | None = None
    if method == "single_llm":
        active_llm_config = load_llm_config(llm_config_path, enabled_override=True if enable_llm else None)
        if llm_client is None:
            llm_client = create_single_llm_client(active_llm_config)

    adapter = ManualAdapter(dataset)
    run_dir = Path(output_root) / run_id
    metrics_dir = run_dir / "metrics"
    diagnoses_dir = run_dir / "diagnoses"
    reports_dir = run_dir / "reports"
    figures_dir = run_dir / "figures"
    tables_dir = run_dir / "tables"
    for path in [metrics_dir, diagnoses_dir, reports_dir, figures_dir, tables_dir]:
        path.mkdir(parents=True, exist_ok=True)

    rows: list[EvalRow] = []
    failure_samples: list[FailureSampleRecord] = []
    scenario_ids = adapter.list_scenarios()
    if limit is not None:
        scenario_ids = scenario_ids[:limit]
    for scenario_id in scenario_ids:
        record = adapter.load_scenario(scenario_id)
        metrics_path = metrics_dir / f"{scenario_id}.json"
        diagnosis_path = diagnoses_dir / f"{scenario_id}.json"
        if resume and metrics_path.is_file() and diagnosis_path.is_file():
            metrics = MetricsRecord.model_validate_json(metrics_path.read_text(encoding="utf-8"))
            diagnosis = DiagnosisRecord.model_validate_json(diagnosis_path.read_text(encoding="utf-8"))
            if diagnosis.method != method:
                raise RuntimeError(
                    f"Cannot resume {run_id}: {scenario_id} was produced by method {diagnosis.method}"
                )
        else:
            metrics, diagnosis = _diagnose(record, method, llm_client)
            _dump_model(metrics, metrics_path)
            _dump_model(diagnosis, diagnosis_path)
        figure_paths = write_scenario_artifacts(record, diagnosis, run_dir)
        _write_report(diagnosis, reports_dir / f"{scenario_id}.md", figure_paths)
        row = evaluate_one(record, diagnosis)
        rows.append(row)
        failure_sample = build_failure_sample(record, diagnosis, row, method=method)
        if failure_sample is not None:
            failure_samples.append(failure_sample)

    summary = summarize(rows)
    confusion = confusion_matrix(rows)
    run_meta = {
        "run_id": run_id,
        "method": method,
        "dataset": str(dataset),
        "threshold_config": "configs/thresholds.yaml",
        "llm_config": str(llm_config_path),
        "git_commit": _git_commit(),
        "seed": seed,
        "scenario_limit": limit,
        "resume": resume,
        "created_at": datetime.now().astimezone().isoformat(),
    }
    if active_llm_config is not None:
        run_meta["llm"] = active_llm_config.public_metadata()
    _write_eval_csv(rows, run_dir / "eval.csv")
    _write_json(summary, run_dir / "summary.json")
    _write_json(confusion, run_dir / "confusion_matrix.json")
    _write_json(run_meta, run_dir / "run_meta.json")
    write_failure_sample_package(run_dir, failure_samples)
    write_run_artifacts(run_dir, rows, summary, confusion, run_meta, failure_sample_count=len(failure_samples))
    return run_dir


def _diagnose(
    record: ScenarioRecord,
    method: str,
    llm_client: SingleLLMClient | None = None,
) -> tuple[MetricsRecord, DiagnosisRecord]:
    if method == "rule_only":
        metrics = run_all_metrics(record)
        return metrics, diagnose_rule_only(record, metrics)
    if method == "single_llm":
        if llm_client is None:
            raise RuntimeError("Single-LLM client is not configured")
        metrics = run_all_metrics(record)
        return metrics, diagnose_single_llm(record, metrics, llm_client)
    return run_diagnosis_graph(record)


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


def _write_report(diagnosis: DiagnosisRecord, path: Path, figure_paths: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(diagnosis, figure_paths), encoding="utf-8")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
