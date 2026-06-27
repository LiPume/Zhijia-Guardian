from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean

from zhijia_guardian.schemas.diagnosis import DiagnosisRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


@dataclass
class EvalRow:
    scenario_id: str
    true_fault_type: str
    pred_fault_type: str
    true_root_module: str
    pred_root_module: str
    true_fault_start_time: float | None
    pred_fault_start_time: float | None
    fault_correct: bool
    root_correct: bool
    fault_time_eligible: bool
    fault_time_predicted: bool
    fault_time_covered: bool
    time_abs_error: float | None
    time_abs_error_at_correct_fault: float | None
    evidence_coverage: float
    evidence_correctness: float
    hallucination_rate: float


def evaluate_one(record: ScenarioRecord, diagnosis: DiagnosisRecord) -> EvalRow:
    oracle = record.load_oracle_for_eval()
    true_fault = oracle.fault_type if oracle and oracle.fault_type else "normal"
    true_root = oracle.root_module if oracle and oracle.root_module else "none"
    true_time = oracle.fault_start_time if oracle else None
    pred_fault = diagnosis.predicted_fault_type or "unknown"
    pred_root = diagnosis.predicted_root_module or "unknown"
    time_error = None
    if true_time is not None and diagnosis.predicted_fault_start_time is not None:
        time_error = abs(diagnosis.predicted_fault_start_time - true_time)
    fault_correct = true_fault == pred_fault
    time_error_at_correct_fault = time_error if fault_correct else None

    coverage, correctness, hallucination = evidence_quality(diagnosis)
    return EvalRow(
        scenario_id=record.scenario_id,
        true_fault_type=true_fault,
        pred_fault_type=pred_fault,
        true_root_module=true_root,
        pred_root_module=pred_root,
        true_fault_start_time=true_time,
        pred_fault_start_time=diagnosis.predicted_fault_start_time,
        fault_correct=fault_correct,
        root_correct=true_root == pred_root,
        fault_time_eligible=true_time is not None,
        fault_time_predicted=diagnosis.predicted_fault_start_time is not None,
        fault_time_covered=true_time is not None and diagnosis.predicted_fault_start_time is not None,
        time_abs_error=time_error,
        time_abs_error_at_correct_fault=time_error_at_correct_fault,
        evidence_coverage=coverage,
        evidence_correctness=correctness,
        hallucination_rate=hallucination,
    )


def summarize(rows: list[EvalRow]) -> dict[str, float | int]:
    labels = sorted(set([row.true_fault_type for row in rows] + [row.pred_fault_type for row in rows]))
    time_errors = [row.time_abs_error for row in rows if row.time_abs_error is not None]
    correct_fault_time_errors = [
        row.time_abs_error_at_correct_fault
        for row in rows
        if row.time_abs_error_at_correct_fault is not None
    ]
    time_eligible = [row for row in rows if row.fault_time_eligible]
    correct_fault_time_eligible = [row for row in time_eligible if row.fault_correct]
    return {
        "num_scenarios": len(rows),
        "fault_accuracy": mean([row.fault_correct for row in rows]) if rows else 0.0,
        "fault_macro_f1": macro_f1(rows, labels),
        "root_top1_accuracy": mean([row.root_correct for row in rows]) if rows else 0.0,
        "module_level_accuracy": mean([row.root_correct for row in rows]) if rows else 0.0,
        "fault_start_time_mae": mean(time_errors) if time_errors else 0.0,
        "fault_start_time_coverage": _ratio(
            sum(row.fault_time_covered for row in time_eligible),
            len(time_eligible),
        ),
        "fault_start_time_mae_at_correct_fault": (
            mean(correct_fault_time_errors) if correct_fault_time_errors else 0.0
        ),
        "fault_start_time_coverage_at_correct_fault": _ratio(
            sum(row.fault_time_covered for row in correct_fault_time_eligible),
            len(correct_fault_time_eligible),
        ),
        "evidence_coverage": mean([row.evidence_coverage for row in rows]) if rows else 0.0,
        "evidence_correctness": mean([row.evidence_correctness for row in rows]) if rows else 0.0,
        "hallucination_rate": mean([row.hallucination_rate for row in rows]) if rows else 0.0,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def macro_f1(rows: list[EvalRow], labels: list[str]) -> float:
    if not rows or not labels:
        return 0.0
    scores = []
    for label in labels:
        tp = sum(row.true_fault_type == label and row.pred_fault_type == label for row in rows)
        fp = sum(row.true_fault_type != label and row.pred_fault_type == label for row in rows)
        fn = sum(row.true_fault_type == label and row.pred_fault_type != label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return mean(scores)


def confusion_matrix(rows: list[EvalRow]) -> list[dict[str, int | str]]:
    labels = sorted(set([row.true_fault_type for row in rows] + [row.pred_fault_type for row in rows]))
    counts = Counter((row.true_fault_type, row.pred_fault_type) for row in rows)
    return [
        {"true_fault_type": true_label, "pred_fault_type": pred_label, "count": counts[(true_label, pred_label)]}
        for true_label in labels
        for pred_label in labels
        if counts[(true_label, pred_label)]
    ]


def evidence_quality(diagnosis: DiagnosisRecord) -> tuple[float, float, float]:
    evidence_by_id = {item.evidence_id: item for item in diagnosis.evidence}
    if not diagnosis.claims:
        return 0.0, 0.0, 1.0

    covered_claims = 0
    hallucinated_claims = 0
    cited_evidence = []
    correct_evidence = 0
    for claim in diagnosis.claims:
        if claim.evidence_ids:
            covered_claims += 1
        claim_supported = False
        for evidence_id in claim.evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                continue
            cited_evidence.append(evidence)
            label = claim.predicted_fault_type
            if label and label in evidence.supports and label not in evidence.contradicts:
                correct_evidence += 1
                claim_supported = True
        if not claim.evidence_ids or not claim_supported:
            hallucinated_claims += 1

    coverage = covered_claims / len(diagnosis.claims)
    correctness = correct_evidence / len(cited_evidence) if cited_evidence else 0.0
    hallucination = hallucinated_claims / len(diagnosis.claims)
    return coverage, correctness, hallucination
