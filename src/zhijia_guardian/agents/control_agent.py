from __future__ import annotations

from zhijia_guardian.agents.scoring import score_evidence
from zhijia_guardian.agents.types import ModuleDiagnosis
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


CONTROL_METRICS = {
    "brake_delay",
}

CONTROL_LABELS = {
    "normal",
    "control_delay",
}


def run_control_agent(scenario: ScenarioRecord, metrics: MetricsRecord) -> ModuleDiagnosis:
    if not any(frame.control.available for frame in scenario.frames):
        return ModuleDiagnosis(
            module_name="control",
            status="skipped",
            summary="Control command is unavailable in this scenario.",
        )
    evidence = [item for item in metrics.evidence if item.metric_name in CONTROL_METRICS]
    return score_evidence("control", evidence, CONTROL_LABELS)
