from __future__ import annotations

from zhijia_guardian.schemas.diagnosis import AgentStepRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


def run_scene_agent(scenario: ScenarioRecord, metrics: MetricsRecord) -> AgentStepRecord:
    timeline = []
    for event in scenario.events_observed:
        timeline.append(
            {
                "time": event.timestamp,
                "type": f"event:{event.event_type}",
                "description": event.description,
            }
        )
    for evidence in metrics.evidence:
        if evidence.status == "violation" and evidence.time is not None:
            timeline.append(
                {
                    "time": evidence.time,
                    "type": f"evidence:{evidence.metric_name}",
                    "description": evidence.description,
                }
            )
    timeline.sort(key=lambda item: item["time"])
    status = "completed" if timeline else "uncertain"
    return AgentStepRecord(
        agent_name="scene_agent",
        status=status,
        summary=f"Built a timeline with {len(timeline)} observed events/evidence items.",
        evidence_ids=[item.evidence_id for item in metrics.evidence if item.status == "violation"],
        output={"timeline": timeline[:20]},
    )
