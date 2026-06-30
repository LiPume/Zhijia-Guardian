from __future__ import annotations

from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.collision import detect_collisions
from zhijia_guardian.tools.comfort_eval import evaluate_comfort
from zhijia_guardian.tools.control_eval import evaluate_control_delay
from zhijia_guardian.tools.evidence import EvidenceFactory
from zhijia_guardian.tools.perception_eval import evaluate_perception
from zhijia_guardian.tools.planning_eval import evaluate_planning
from zhijia_guardian.tools.ttc import compute_ttc


def run_all_metrics(scenario: ScenarioRecord) -> MetricsRecord:
    factory = EvidenceFactory()
    evidence = []
    series = []
    ttc = compute_ttc(scenario, factory=factory)
    collision = detect_collisions(scenario, factory=factory)
    perception = evaluate_perception(scenario, factory=factory)
    planning = evaluate_planning(scenario, factory=factory)
    control = evaluate_control_delay(scenario, ttc.risk_start_time, ttc.min_ttc, factory=factory)
    comfort = evaluate_comfort(scenario, factory=factory)
    for result in [ttc, collision, perception, planning, control, comfort]:
        evidence.extend(result.evidence)
    series.extend(comfort.series)
    return MetricsRecord(scenario_id=scenario.scenario_id, series=series, evidence=evidence)
