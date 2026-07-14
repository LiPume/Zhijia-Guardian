import pytest

from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow import run_diagnostic_workflow


@pytest.mark.parametrize(("kind", "topic", "link"), [
  ("perception_dropout", "perceptionEvidence", "perceptionEvidence -> longitudinalPlan"),
  ("planner_gap", "longitudinalPlan", "longitudinalPlan -> carControl"),
  ("sendcan_gap", "sendcan", "carControl -> sendcan"),
])
def test_fault_family_uses_same_active_repair_loop(kind, topic, link):
  clean = generate_clean_case()
  perturbed, _ = inject_perturbation(clean, kind=kind, topic=topic)
  diagnosis, state = run_diagnostic_workflow(perturbed, intervention_reference=clean)
  assert diagnosis.findings[0].classification == "validated_root_cause"
  assert diagnosis.findings[0].suspected_link == link
  assert state.validations[0].status == "confirmed"
