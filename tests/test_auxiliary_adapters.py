import json

from zhijia_guardian.adapters import generate_clean_case, inject_perturbation, load_nuplan_planning_evidence, load_nuscenes_perception_evidence
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_auxiliary_adapters_preserve_not_same_route_boundary(tmp_path):
  nuscenes_path = tmp_path / "nuscenes.json"
  nuscenes_path.write_text(json.dumps({"bundle_id": "nusc-1", "source_reference": "scene-token", "observations": {"detector_recall": 0.5}}))
  nuplan_path = tmp_path / "nuplan.json"
  nuplan_path.write_text(json.dumps({"bundle_id": "nuplan-1", "source_reference": "scenario-token", "observations": {"trajectory_gap_s": 0.2}}))
  bundles = [load_nuscenes_perception_evidence(nuscenes_path), load_nuplan_planning_evidence(nuplan_path)]
  case, _ = inject_perturbation(generate_clean_case())
  diagnosis, state = run_diagnostic_workflow(case, auxiliary_evidence=bundles)
  assert all(not item.same_route_as_primary for item in state.case.auxiliary_evidence)
  assert diagnosis.audit.status == "downgraded"
  assert any("not treated as a shared physical route" in issue for issue in diagnosis.audit.issues)
