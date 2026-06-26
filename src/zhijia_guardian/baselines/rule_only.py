from __future__ import annotations

from collections import defaultdict

from zhijia_guardian.schemas.diagnosis import ClaimRecord, DiagnosisRecord, EvidenceRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


ROOT_MODULE = {
    "normal": "none",
    "perception_miss": "perception",
    "perception_false_positive": "perception",
    "perception_confidence_drop": "perception",
    "perception_class_confusion": "perception",
    "planning_collision_risk": "planning",
    "control_delay": "control",
}


def diagnose_rule_only(scenario: ScenarioRecord, metrics: MetricsRecord) -> DiagnosisRecord:
    scores: dict[str, float] = defaultdict(float)
    supporting_evidence: dict[str, list[EvidenceRecord]] = defaultdict(list)

    for evidence in metrics.evidence:
        for label in evidence.supports:
            weight = _weight(evidence.metric_name, label)
            scores[label] += weight
            supporting_evidence[label].append(evidence)
        for label in evidence.contradicts:
            scores[label] -= 0.5

    predicted = _choose_label(scores)
    root_module = ROOT_MODULE.get(predicted, "unknown")
    predicted_evidence = supporting_evidence.get(predicted, [])
    start_time = None if predicted == "normal" else _earliest_time(predicted_evidence)
    evidence_ids = [e.evidence_id for e in predicted_evidence]

    claim = ClaimRecord(
        claim_id="C_001",
        claim=f"Rule-only baseline predicts {predicted}.",
        predicted_fault_type=predicted,
        predicted_root_module=root_module,
        evidence_ids=evidence_ids,
    )
    confidence = min(1.0, max(0.0, scores.get(predicted, 0.0) / 5.0))
    return DiagnosisRecord(
        scenario_id=scenario.scenario_id,
        predicted_fault_type=predicted,
        predicted_root_module=root_module,
        predicted_fault_start_time=start_time,
        confidence=confidence,
        evidence=metrics.evidence,
        claims=[claim],
    )


def _choose_label(scores: dict[str, float]) -> str:
    candidate_scores = {label: score for label, score in scores.items() if score > 0}
    if not candidate_scores:
        return "normal"
    priority = [
        "control_delay",
        "perception_confidence_drop",
        "perception_miss",
        "perception_false_positive",
        "perception_class_confusion",
        "planning_collision_risk",
        "normal",
    ]
    return max(candidate_scores, key=lambda label: (candidate_scores[label], -priority.index(label) if label in priority else -999))


def _earliest_time(evidence: list[EvidenceRecord]) -> float | None:
    times = [item.time for item in evidence if item.time is not None]
    return min(times) if times else None


def _weight(metric_name: str, label: str) -> float:
    if metric_name == "brake_delay" and label == "control_delay":
        return 4.0
    if metric_name == "confidence_drop_events" and label == "perception_confidence_drop":
        return 4.0
    if metric_name in {"missed_key_actors", "false_positives", "class_confusions"}:
        return 3.0
    if metric_name == "trajectory_collision_count" and label == "planning_collision_risk":
        return 3.0
    if metric_name in {"min_ttc", "collision_count"}:
        return 1.0
    if label == "normal":
        return 1.0
    return 1.0
