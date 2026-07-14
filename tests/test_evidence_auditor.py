from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_findings_have_known_evidence_and_no_oracle_access():
  case, _ = inject_perturbation(generate_clean_case())
  diagnosis, state = run_diagnostic_workflow(case)
  known = {item.evidence_id for item in state.case.evidence}
  assert state.case.oracle is None
  assert diagnosis.audit.status in {"passed", "downgraded"}
  assert all(set(finding.evidence_ids) <= known for finding in diagnosis.findings)
