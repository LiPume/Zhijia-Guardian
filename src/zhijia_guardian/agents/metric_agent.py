from __future__ import annotations

from zhijia_guardian.schemas.diagnosis import AgentStepRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.run_metrics import run_all_metrics


def run_metric_agent(scenario: ScenarioRecord) -> tuple[MetricsRecord, AgentStepRecord]:
    metrics = run_all_metrics(scenario)
    return metrics, AgentStepRecord(
        agent_name="metric_agent",
        status="completed",
        summary=f"Calculated {len(metrics.evidence)} evidence records.",
        evidence_ids=[item.evidence_id for item in metrics.evidence],
        output={"num_evidence": len(metrics.evidence)},
    )
