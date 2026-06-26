from __future__ import annotations

from zhijia_guardian.agents.scoring import score_evidence
from zhijia_guardian.agents.types import ModuleDiagnosis
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


PERCEPTION_METRICS = {
    "missed_key_actors",
    "false_positives",
    "class_confusions",
    "confidence_drop_events",
    "perception_anomalies",
}

PERCEPTION_LABELS = {
    "normal",
    "perception_miss",
    "perception_false_positive",
    "perception_confidence_drop",
    "perception_class_confusion",
}


def run_perception_agent(scenario: ScenarioRecord, metrics: MetricsRecord) -> ModuleDiagnosis:
    if not any(frame.perception.available for frame in scenario.frames):
        return ModuleDiagnosis(
            module_name="perception",
            status="skipped",
            summary="Perception output is unavailable in this scenario.",
        )
    evidence = [item for item in metrics.evidence if item.metric_name in PERCEPTION_METRICS]
    return score_evidence("perception", evidence, PERCEPTION_LABELS)
