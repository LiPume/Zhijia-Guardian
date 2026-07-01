from __future__ import annotations

from collections import defaultdict

from zhijia_guardian.agents.types import ModuleDiagnosis
from zhijia_guardian.schemas.diagnosis import EvidenceRecord


ROOT_MODULE = {
    "normal": "none",
    "perception_miss": "perception",
    "perception_false_positive": "perception",
    "perception_confidence_drop": "perception",
    "perception_class_confusion": "perception",
    "planning_collision_risk": "planning",
    "control_delay": "control",
}


LABEL_PRIORITY = [
    "control_delay",
    "perception_miss",
    "perception_confidence_drop",
    "perception_false_positive",
    "perception_class_confusion",
    "planning_collision_risk",
    "normal",
]


def score_evidence(
    module_name: str,
    evidence: list[EvidenceRecord],
    allowed_labels: set[str],
) -> ModuleDiagnosis:
    if not evidence:
        return ModuleDiagnosis(
            module_name=module_name,
            status="skipped",
            predicted_fault_type=None,
            predicted_root_module=None,
            summary=f"{module_name} has no diagnosable evidence.",
        )

    scores: dict[str, float] = defaultdict(float)
    supporting: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for item in evidence:
        for label in item.supports:
            if label not in allowed_labels:
                continue
            scores[label] += _weight(item.metric_name, label)
            supporting[label].append(item)
        for label in item.contradicts:
            if label in allowed_labels:
                scores[label] -= 0.5

    predicted = _choose_label(scores)
    if predicted is None:
        return ModuleDiagnosis(
            module_name=module_name,
            status="uncertain",
            score=0.0,
            evidence=evidence,
            summary=f"{module_name} found evidence, but no allowed label is strongly supported.",
        )

    chosen_evidence = supporting.get(predicted, evidence if predicted == "normal" else [])
    score = max(scores.get(predicted, 0.0), 0.0)
    return ModuleDiagnosis(
        module_name=module_name,
        status="completed",
        predicted_fault_type=predicted,
        predicted_root_module=ROOT_MODULE.get(predicted, module_name),
        score=score,
        confidence=min(1.0, score / 5.0),
        start_time=_earliest_time(chosen_evidence),
        evidence=chosen_evidence,
        summary=f"{module_name} predicts {predicted}.",
    )


def _choose_label(scores: dict[str, float]) -> str | None:
    candidate_scores = {label: score for label, score in scores.items() if score > 0}
    if not candidate_scores:
        return None
    return max(
        candidate_scores,
        key=lambda label: (
            candidate_scores[label],
            -LABEL_PRIORITY.index(label) if label in LABEL_PRIORITY else -999,
        ),
    )


def _earliest_time(evidence: list[EvidenceRecord]) -> float | None:
    times = [item.time for item in evidence if item.time is not None]
    return min(times) if times else None


def _weight(metric_name: str, label: str) -> float:
    if metric_name == "brake_delay" and label == "control_delay":
        return 4.0
    if metric_name == "confidence_drop_events" and label == "perception_confidence_drop":
        return 3.0
    if metric_name in {"missed_key_actors", "false_positives", "class_confusions"}:
        return 3.0
    if metric_name == "trajectory_collision_count" and label == "planning_collision_risk":
        return 3.0
    if metric_name in {"min_ttc", "collision_count"} and label != "normal":
        return 1.0
    if label == "normal":
        return 1.0
    return 1.0
