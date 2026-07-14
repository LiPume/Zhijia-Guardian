from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_priority_score_prefers_native_upstream_model_in_ambiguous_case():
  clean = generate_clean_case()
  ambiguous, _ = inject_perturbation(clean, kind="perception_and_sendcan_gap")
  diagnosis, state = run_diagnostic_workflow(ambiguous, intervention_reference=clean)
  assert {item.hypothesis_type for item in state.hypotheses} == {"propagation", "independent_fault", "common_cause", "insufficient_observability"}
  assert state.decision_board is not None
  assert state.decision_board.chosen_action_id == "act-hyp-001"
  assert state.interventions[0].action == "restore_baseline_modelV2"
  assert diagnosis.findings[0].suspected_link == "modelV2 -> longitudinalPlan"
  selected = next(item for item in state.decision_board.action_candidates if item.action_id == state.decision_board.chosen_action_id)
  assert selected.diagnostic_priority_score > 0
  assert "downstream_explanatory_coverage" in selected.score_components
