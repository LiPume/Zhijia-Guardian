from __future__ import annotations

from zhijia_guardian.agents.scoring import score_evidence
from zhijia_guardian.agents.types import ModuleDiagnosis
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord, TrajectorySource


PLANNING_METRICS = {
    "trajectory_collision_count",
}

PLANNING_LABELS = {
    "normal",
    "planning_collision_risk",
}

DIAGNOSABLE_SOURCES = {
    TrajectorySource.OFFLINE_PLANNER,
    TrajectorySource.PERTURBED_PLANNER,
    TrajectorySource.MODEL_PREDICTION,
}


def run_planning_agent(scenario: ScenarioRecord, metrics: MetricsRecord) -> ModuleDiagnosis:
    if not any(frame.planning.available for frame in scenario.frames):
        return ModuleDiagnosis(
            module_name="planning",
            status="skipped",
            summary="Planning trajectory is unavailable in this scenario.",
        )
    if not any(frame.planning.trajectory_source in DIAGNOSABLE_SOURCES for frame in scenario.frames):
        return ModuleDiagnosis(
            module_name="planning",
            status="skipped",
            summary="Planning trajectory is reference/expert data, not a diagnosable planner output.",
        )
    evidence = [item for item in metrics.evidence if item.metric_name in PLANNING_METRICS]
    return score_evidence("planning", evidence, PLANNING_LABELS)
