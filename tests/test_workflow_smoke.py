from pathlib import Path

from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.reporting import write_artifacts
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_workflow_generates_required_artifacts(tmp_path: Path):
  case, _ = inject_perturbation(generate_clean_case())
  diagnosis, state = run_diagnostic_workflow(case)
  paths = write_artifacts(tmp_path, state.case, diagnosis, state.trace)
  assert {"case_manager", "message_flow_agent", "evidence_auditor", "report_agent"} <= {entry.agent for entry in state.trace}
  assert diagnosis.findings[0].classification == "suspected_link"
  for name in ("diagnosis", "evidence", "trace", "report", "package"):
    assert paths[name].exists()
