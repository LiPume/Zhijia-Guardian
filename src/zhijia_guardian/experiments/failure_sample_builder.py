from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from zhijia_guardian.experiments.eval_metrics import EvalRow
from zhijia_guardian.schemas.diagnosis import DiagnosisRecord, EvidenceRecord
from zhijia_guardian.schemas.failure_sample import (
    ExpectedDiagnosis,
    FailureSampleRecord,
    FailureSampleSource,
    RecommendedDataRecord,
    RegressionTestConfig,
    ScenarioSelector,
)
from zhijia_guardian.schemas.scenario import ScenarioRecord


def build_failure_sample(
    record: ScenarioRecord,
    diagnosis: DiagnosisRecord,
    eval_row: EvalRow,
    method: str,
    threshold_config: str = "configs/thresholds.yaml",
    llm_config: str = "configs/llm.yaml",
) -> FailureSampleRecord | None:
    should_export = (
        eval_row.true_fault_type != "normal"
        or not eval_row.fault_correct
        or not eval_row.root_correct
    )
    if not should_export:
        return None

    selected_evidence = _select_evidence(
        diagnosis=diagnosis,
        true_fault_type=eval_row.true_fault_type,
        pred_fault_type=eval_row.pred_fault_type,
    )
    evidence_ids = [item.evidence_id for item in selected_evidence]
    correct = eval_row.fault_correct and eval_row.root_correct
    source_generation = record.source.generation

    return FailureSampleRecord(
        scenario_id=record.scenario_id,
        source=FailureSampleSource(
            dataset=record.source.dataset,
            version=record.source.version,
            raw_log_id=record.source.raw_log_id,
            raw_tokens=record.source.raw_tokens,
        ),
        diagnosis_method=method,
        predicted_fault_type=eval_row.pred_fault_type,
        predicted_root_module=eval_row.pred_root_module,
        predicted_fault_start_time=eval_row.pred_fault_start_time,
        true_fault_type=eval_row.true_fault_type,
        true_root_module=eval_row.true_root_module,
        true_fault_start_time=eval_row.true_fault_start_time,
        is_correct=correct,
        confidence=diagnosis.confidence,
        evidence=selected_evidence,
        wrong_reasoning=_wrong_reasoning(eval_row, evidence_ids),
        correct_reasoning=_correct_reasoning(eval_row, selected_evidence),
        tags=_tags(eval_row, method, record, source_generation),
        recommended_data=_recommended_data(eval_row.true_root_module, eval_row.true_fault_type),
        regression_test_config=_regression_test_config(
            eval_row=eval_row,
            record=record,
            method=method,
            threshold_config=threshold_config,
            llm_config=llm_config,
        ),
        scenario_record_hash=scenario_record_hash(record),
    )


def write_failure_sample_package(run_dir: Path, samples: list[FailureSampleRecord]) -> None:
    failure_root = run_dir / "failure_samples"
    tables_dir = run_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    if failure_root.exists():
        shutil.rmtree(failure_root)
    failure_root.mkdir(parents=True, exist_ok=True)

    for sample in samples:
        package_dir = failure_root / sample.scenario_id
        package_dir.mkdir(parents=True, exist_ok=True)
        _write_json(sample, package_dir / "failure_sample.json")

    with (run_dir / "failure_samples.jsonl").open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample.model_dump(mode="json", exclude_none=True), ensure_ascii=False, sort_keys=True))
            f.write("\n")

    _write_failure_samples_csv(samples, tables_dir / "failure_samples.csv")


def scenario_record_hash(record: ScenarioRecord) -> str:
    payload = json.dumps(
        record.observed_view(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _select_evidence(
    diagnosis: DiagnosisRecord,
    true_fault_type: str,
    pred_fault_type: str,
) -> list[EvidenceRecord]:
    cited_ids = {
        evidence_id
        for claim in diagnosis.claims
        for evidence_id in claim.evidence_ids
    }
    selected: list[EvidenceRecord] = []
    for item in diagnosis.evidence:
        if (
            item.evidence_id in cited_ids
            or item.status == "violation"
            or true_fault_type in item.supports
            or pred_fault_type in item.supports
            or true_fault_type in item.contradicts
            or pred_fault_type in item.contradicts
        ):
            selected.append(item)
    return selected or diagnosis.evidence[:12]


def _wrong_reasoning(eval_row: EvalRow, evidence_ids: list[str]) -> str:
    if eval_row.fault_correct and eval_row.root_correct:
        return "No wrong reasoning: the diagnosis matches the evaluation oracle."

    cited = ", ".join(evidence_ids) if evidence_ids else "no cited evidence"
    return (
        "Prediction mismatch. "
        f"Predicted {eval_row.pred_fault_type}/{eval_row.pred_root_module}, "
        f"but the oracle is {eval_row.true_fault_type}/{eval_row.true_root_module}. "
        f"Review cited evidence: {cited}."
    )


def _correct_reasoning(eval_row: EvalRow, evidence: list[EvidenceRecord]) -> str:
    supporting = [
        item.evidence_id
        for item in evidence
        if (
            eval_row.true_fault_type in item.supports
            or (eval_row.true_fault_type == "normal" and "normal" in item.supports)
        )
    ]
    if supporting:
        return (
            f"Oracle-consistent reasoning: {eval_row.true_fault_type}/"
            f"{eval_row.true_root_module} is supported by {', '.join(supporting)}."
        )
    return (
        f"Oracle label is {eval_row.true_fault_type}/{eval_row.true_root_module}. "
        "The current diagnosis did not retain direct supporting evidence for this label."
    )


def _tags(
    eval_row: EvalRow,
    method: str,
    record: ScenarioRecord,
    source_generation: dict[str, Any],
) -> list[str]:
    tags = [
        f"dataset:{record.source.dataset}",
        f"version:{record.source.version}",
        f"method:{method}",
        f"true_fault:{eval_row.true_fault_type}",
        f"pred_fault:{eval_row.pred_fault_type}",
        f"true_root:{eval_row.true_root_module}",
        f"pred_root:{eval_row.pred_root_module}",
        "eval_status:correct" if eval_row.fault_correct and eval_row.root_correct else "eval_status:error",
    ]
    if record.source.raw_log_id:
        tags.append(f"raw_log_id:{record.source.raw_log_id}")
    for key in ("scenario_family", "difficulty", "noise_profile"):
        value = source_generation.get(key)
        if value:
            tags.append(f"{key}:{value}")
    return tags


def _recommended_data(root_module: str, fault_type: str) -> list[RecommendedDataRecord]:
    common = [
        {
            "name": "canonical_observed_scenario",
            "reason": "Replay the same observed-only input used by diagnosis.",
            "priority": "high",
        },
        {
            "name": "oracle_review_record",
            "reason": "Keep the hidden evaluation label separate for offline replay checks.",
            "priority": "high",
        },
    ]
    by_root = {
        "perception": [
            {
                "name": "sensor_clip_and_detection_tracks",
                "reason": "Inspect object visibility, confidence trend, miss/false-positive timing, and matching quality.",
                "priority": "high",
            },
            {
                "name": "annotation_or_offline_reconstruction",
                "reason": "Verify high-risk actors and object association around the fault window.",
                "priority": "medium",
            },
        ],
        "planning": [
            {
                "name": "planned_trajectory_and_cost_debug",
                "reason": "Compare candidate path, obstacle interaction, lane context, and collision/TTC risk.",
                "priority": "high",
            },
            {
                "name": "map_and_route_context",
                "reason": "Check drivable area, lane topology, route progress, and speed-limit assumptions.",
                "priority": "medium",
            },
        ],
        "control": [
            {
                "name": "control_command_and_actuator_feedback",
                "reason": "Measure brake/throttle/steer latency, saturation, and command tracking.",
                "priority": "high",
            },
            {
                "name": "ego_dynamics_trace",
                "reason": "Inspect acceleration, jerk, and response timing near the fault window.",
                "priority": "medium",
            },
        ],
    }
    fault_specific = {
        "name": f"fault_window_{fault_type}",
        "reason": "Slice data around the oracle fault start time for regression and annotation review.",
        "priority": "high",
    }
    return [
        RecommendedDataRecord.model_validate(item)
        for item in common + by_root.get(root_module, []) + [fault_specific]
    ]


def _regression_test_config(
    eval_row: EvalRow,
    record: ScenarioRecord,
    method: str,
    threshold_config: str,
    llm_config: str,
) -> RegressionTestConfig:
    return RegressionTestConfig(
        scenario_selector=ScenarioSelector(
            scenario_id=record.scenario_id,
            dataset=record.source.dataset,
            version=record.source.version,
            raw_log_id=record.source.raw_log_id,
        ),
        method_under_test=method,
        threshold_config=threshold_config,
        llm_config=llm_config,
        expected=ExpectedDiagnosis(
            fault_type=eval_row.true_fault_type,
            root_module=eval_row.true_root_module,
            fault_start_time=eval_row.true_fault_start_time,
        ),
    )


def _write_failure_samples_csv(samples: list[FailureSampleRecord], path: Path) -> None:
    fieldnames = [
        "scenario_id",
        "true_fault_type",
        "predicted_fault_type",
        "true_root_module",
        "predicted_root_module",
        "is_correct",
        "package_path",
        "scenario_record_hash",
        "tags",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for sample in samples:
            scenario_id = sample.scenario_id
            writer.writerow(
                {
                    "scenario_id": scenario_id,
                    "true_fault_type": sample.true_fault_type,
                    "predicted_fault_type": sample.predicted_fault_type,
                    "true_root_module": sample.true_root_module,
                    "predicted_root_module": sample.predicted_root_module,
                    "is_correct": sample.is_correct,
                    "package_path": f"failure_samples/{scenario_id}/failure_sample.json",
                    "scenario_record_hash": sample.scenario_record_hash,
                    "tags": ";".join(sample.tags),
                }
            )


def _write_json(data: FailureSampleRecord, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data.model_dump(mode="json", exclude_none=True),
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")
