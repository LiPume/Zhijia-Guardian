from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_information_gain_policy_prefers_upstream_perception_in_ambiguous_case():
  clean = generate_clean_case()
  ambiguous, _ = inject_perturbation(clean, kind="perception_and_sendcan_gap")
  diagnosis, state = run_diagnostic_workflow(ambiguous, intervention_reference=clean)
  assert len(state.hypotheses) == 2
  assert state.decision_board is not None
  assert state.decision_board.chosen_action_id == "act-hyp-001"
  assert state.interventions[0].action == "restore_baseline_perceptionEvidence"
  assert diagnosis.findings[0].suspected_link == "perceptionEvidence -> longitudinalPlan"
