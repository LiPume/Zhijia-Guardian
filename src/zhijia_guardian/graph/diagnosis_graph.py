from __future__ import annotations

from zhijia_guardian.agents.control_agent import run_control_agent
from zhijia_guardian.agents.metric_agent import run_metric_agent
from zhijia_guardian.agents.perception_agent import run_perception_agent
from zhijia_guardian.agents.planning_agent import run_planning_agent
from zhijia_guardian.agents.root_cause_agent import run_root_cause_agent
from zhijia_guardian.agents.scene_agent import run_scene_agent
from zhijia_guardian.schemas.diagnosis import AgentStepRecord, DiagnosisRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


def run_diagnosis_graph(
    scenario: ScenarioRecord,
    metrics: MetricsRecord | None = None,
) -> tuple[MetricsRecord, DiagnosisRecord]:
    observed = scenario.observed_view()
    if "oracle" in observed:
        raise AssertionError("oracle leaked into diagnosis graph observed view")

    trace: list[AgentStepRecord] = []
    if metrics is None:
        metrics, metric_trace = run_metric_agent(scenario)
        trace.append(metric_trace)
    else:
        trace.append(
            AgentStepRecord(
                agent_name="metric_agent",
                status="completed",
                summary=f"Received precomputed metrics with {len(metrics.evidence)} evidence records.",
                evidence_ids=[item.evidence_id for item in metrics.evidence],
                output={"num_evidence": len(metrics.evidence), "precomputed": True},
            )
        )

    trace.append(run_scene_agent(scenario, metrics))
    module_diagnoses = [
        run_perception_agent(scenario, metrics),
        run_planning_agent(scenario, metrics),
        run_control_agent(scenario, metrics),
    ]
    diagnosis = run_root_cause_agent(scenario, metrics, module_diagnoses, trace)
    return metrics, diagnosis
