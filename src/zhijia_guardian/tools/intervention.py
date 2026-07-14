from __future__ import annotations

from zhijia_guardian.schema.models import DiagnosticCase, Hypothesis, Intervention, ToolResult, ValidationResult
from .evidence import create_evidence, result
from .message_flow import detect_message_gaps


def run_counterfactual_repair(case: DiagnosticCase, reference: DiagnosticCase | None, hypothesis: Hypothesis) -> tuple[Intervention, ToolResult, DiagnosticCase | None]:
  if not case.source.is_synthetic or reference is None:
    intervention = Intervention(intervention_id=f"int-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, action="counterfactual_repair", target_link=hypothesis.target_link,
      feasible=False, status="not_feasible", rationale="No controllable synthetic reference is available; a real log cannot be silently modified as evidence.")
    tool = result("run_counterfactual_repair", "insufficient_observability", limitations=[intervention.rationale])
    return intervention, tool, None
  target_topic = {"perceptionEvidence -> longitudinalPlan": "perceptionEvidence", "longitudinalPlan -> carControl": "longitudinalPlan", "carControl -> sendcan": "sendcan"}.get(hypothesis.target_link)
  if target_topic is None:
    intervention = Intervention(intervention_id=f"int-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, action="counterfactual_repair", target_link=hypothesis.target_link,
      feasible=False, status="not_feasible", rationale="No deterministic repair model exists for this link.")
    return intervention, result("run_counterfactual_repair", "insufficient_observability", limitations=[intervention.rationale]), None
  repaired = case.model_copy(deep=True)
  existing = {message.raw_reference for message in repaired.messages}
  restored = [message.model_copy(deep=True) for message in reference.messages if message.topic == target_topic and message.raw_reference not in existing]
  repaired.messages.extend(restored)
  repaired.messages.sort(key=lambda message: message.mono_time)
  repaired.case_id = f"{case.case_id}-counterfactual-repair"
  evidence = create_evidence("counterfactual_intervention", f"Restored {len(restored)} baseline {target_topic} messages in a synthetic repair replay.", "run_counterfactual_repair", topic=target_topic, source_scope="validation", metrics={"restored_messages": len(restored)})
  intervention = Intervention(intervention_id=f"int-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, action=f"restore_baseline_{target_topic}", target_link=hypothesis.target_link,
    feasible=True, status="executed", rationale="Synthetic reference provides a deterministic counterfactual repair.", evidence_ids=[evidence.evidence_id])
  return intervention, result("run_counterfactual_repair", "ok", metrics={"restored_messages": len(restored)}, evidence=[evidence]), repaired


def validate_counterfactual(hypothesis: Hypothesis, repaired: DiagnosticCase | None, intervention: Intervention) -> tuple[ValidationResult, ToolResult]:
  if repaired is None:
    evidence = create_evidence("validation_unavailable", "Counterfactual validation was not feasible for this case.", "validate_counterfactual", source_scope="validation")
    return ValidationResult(validation_id=f"val-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, status="insufficient_evidence", expected_observation=hypothesis.expected_observation,
      observed_result="No controllable replay was available.", confidence_delta=0.0, evidence_ids=[evidence.evidence_id]), result("validate_counterfactual", "insufficient_observability", evidence=[evidence])
  target_topic = {"perceptionEvidence -> longitudinalPlan": "perceptionEvidence", "longitudinalPlan -> carControl": "longitudinalPlan", "carControl -> sendcan": "sendcan"}.get(hypothesis.target_link, "sendcan")
  gap = detect_message_gaps(repaired, target_topic)
  confirmed = gap.metrics.get("gap_count", 0) == 0
  evidence = create_evidence("counterfactual_validation", f"Repair replay {'removed' if confirmed else 'did not remove'} the direct {target_topic} gap.", "validate_counterfactual", topic=target_topic, source_scope="validation",
    metrics={"remaining_gap_count": gap.metrics.get("gap_count", 0)})
  validation = ValidationResult(validation_id=f"val-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, status="confirmed" if confirmed else "refuted",
    expected_observation=hypothesis.expected_observation, observed_result=evidence.summary, confidence_delta=0.25 if confirmed else -0.35, evidence_ids=[evidence.evidence_id])
  return validation, result("validate_counterfactual", "ok", metrics=evidence.metrics, evidence=[evidence])
