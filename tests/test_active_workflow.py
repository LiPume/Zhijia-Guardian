from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_synthetic_repair_validates_only_controlled_fault_mechanism():
  clean = generate_clean_case()
  perturbed, _ = inject_perturbation(clean)
  diagnosis, state = run_diagnostic_workflow(perturbed, intervention_reference=clean)
  assert diagnosis.findings[0].classification == "counterfactually_supported_injected_fault_location"
  assert [item.role for item in state.interventions] == ["targeted_repair", "sham_repair", "alternative_repair"]
  assert state.interventions[0].status == "executed"
  assert state.validations[0].status == "confirmed"
  assert state.validations[0].check_outcomes == {
    "targeted_direct_gap_removed": True,
    "sham_preserved_target_gap": True,
    "alternative_preserved_target_gap": True,
  }
  assert "real-world root cause" in diagnosis.findings[0].statement


def test_real_like_case_never_runs_synthetic_repair_or_claims_validated_root():
  case, _ = inject_perturbation(generate_clean_case())
  case.source.is_synthetic = False
  diagnosis, state = run_diagnostic_workflow(case)
  assert state.interventions[0].status == "not_feasible"
  assert all(item.classification != "counterfactually_supported_injected_fault_location" for item in diagnosis.findings)
