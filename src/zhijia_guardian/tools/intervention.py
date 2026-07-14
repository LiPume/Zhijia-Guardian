from __future__ import annotations

from zhijia_guardian.schema.models import DiagnosticCase, Hypothesis, Intervention, ToolResult, ValidationResult
from .evidence import create_evidence, result
from .message_flow import detect_message_gaps


_TARGET_TOPICS = {
  "modelV2 -> longitudinalPlan": "modelV2",
  "longitudinalPlan -> carControl": "longitudinalPlan",
  "carControl -> sendcan": "sendcan",
}


def _control_topic(case: DiagnosticCase, target_topic: str, role: str) -> str | None:
  if role == "targeted_repair":
    return target_topic
  if role == "alternative_repair":
    upstream = [source for source, destinations in case.dependency_graph.items() if target_topic in destinations]
    return upstream[0] if upstream else next((topic for topic in ("carControl", "longitudinalPlan", "modelV2") if topic != target_topic), None)
  return next((topic for topic in ("pandaStates", "can", "carState", "controlsState") if topic != target_topic and any(msg.topic == topic for msg in case.messages)), None)


def run_counterfactual_repair(case: DiagnosticCase, reference: DiagnosticCase | None, hypothesis: Hypothesis, *, role: str = "targeted_repair") -> tuple[Intervention, ToolResult, DiagnosticCase | None]:
  """Create a named targeted/sham/alternative replay without exposing oracle data."""
  if not case.source.is_synthetic or reference is None:
    intervention = Intervention(
      intervention_id=f"int-{hypothesis.hypothesis_id}-{role}", hypothesis_id=hypothesis.hypothesis_id, action="counterfactual_repair", target_link=hypothesis.target_link,
      feasible=False, status="not_feasible", role="observation_request", rationale="No controllable synthetic reference is available; a real log cannot be silently modified as evidence.",
    )
    tool = result("run_counterfactual_repair", "insufficient_observability", limitations=[intervention.rationale])
    return intervention, tool, None
  target_topic = _TARGET_TOPICS.get(hypothesis.target_link)
  restore_topic = _control_topic(case, target_topic, role) if target_topic else None
  if hypothesis.hypothesis_type != "propagation" or restore_topic is None:
    intervention = Intervention(
      intervention_id=f"int-{hypothesis.hypothesis_id}-{role}", hypothesis_id=hypothesis.hypothesis_id, action="counterfactual_repair", target_link=hypothesis.target_link,
      feasible=False, status="not_feasible", role="observation_request", rationale="No deterministic repair model exists for this competing explanation.",
    )
    return intervention, result("run_counterfactual_repair", "insufficient_observability", limitations=[intervention.rationale]), None
  repaired = case.model_copy(deep=True)
  existing = {message.raw_reference for message in repaired.messages}
  restored = [message.model_copy(deep=True) for message in reference.messages if message.topic == restore_topic and message.raw_reference not in existing]
  repaired.messages.extend(restored)
  repaired.messages.sort(key=lambda message: message.mono_time)
  repaired.case_id = f"{case.case_id}-{role}"
  evidence = create_evidence(
    "counterfactual_intervention", f"{role} restored {len(restored)} baseline {restore_topic} messages in a synthetic replay.", "run_counterfactual_repair",
    topic=restore_topic, source_scope="validation", metrics={"restored_messages": len(restored), "role": role, "target_topic": target_topic},
  )
  intervention = Intervention(
    intervention_id=f"int-{hypothesis.hypothesis_id}-{role}", hypothesis_id=hypothesis.hypothesis_id, action=f"restore_baseline_{restore_topic}", target_link=hypothesis.target_link,
    feasible=True, status="executed", role=role, rationale="Synthetic reference is used only as a named counterfactual control; oracle remains unavailable to the workflow.", evidence_ids=[evidence.evidence_id],
  )
  return intervention, result("run_counterfactual_repair", "ok", metrics=evidence.metrics, evidence=[evidence]), repaired


def validate_counterfactual(hypothesis: Hypothesis, replays: dict[str, DiagnosticCase | None], interventions: list[Intervention]) -> tuple[ValidationResult, ToolResult]:
  target_topic = _TARGET_TOPICS.get(hypothesis.target_link)
  if target_topic is None or not replays.get("targeted_repair"):
    evidence = create_evidence("validation_unavailable", "Counterfactual validation was not feasible for this case.", "validate_counterfactual", source_scope="validation")
    return ValidationResult(
      validation_id=f"val-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, status="insufficient_evidence", expected_observation=hypothesis.expected_observation,
      observed_result="No controllable targeted replay was available.", confidence_delta=0.0, evidence_ids=[evidence.evidence_id], limitations=["No synthetic targeted repair replay."],
    ), result("validate_counterfactual", "insufficient_observability", evidence=[evidence])
  gaps = {role: detect_message_gaps(replay, target_topic).metrics.get("gap_count", -1) if replay else -1 for role, replay in replays.items()}
  checks = {
    "targeted_direct_gap_removed": gaps.get("targeted_repair", -1) == 0,
    "sham_preserved_target_gap": gaps.get("sham_repair", -1) > 0,
    "alternative_preserved_target_gap": gaps.get("alternative_repair", -1) > 0,
  }
  confirmed = all(checks.values())
  evidence = create_evidence(
    "counterfactual_validation",
    "Targeted repair removed the direct gap while sham and alternative repairs preserved it." if confirmed else "Counterfactual controls did not cleanly distinguish the target fault location.",
    "validate_counterfactual", topic=target_topic, source_scope="validation", metrics={"remaining_gap_count_by_replay": gaps, "checks": checks, "intervention_count": len(interventions)},
    limitations=["This validates only an injected synthetic fault location; no downstream propagation mechanism is claimed."],
  )
  validation = ValidationResult(
    validation_id=f"val-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, status="confirmed" if confirmed else "refuted",
    expected_observation=hypothesis.expected_observation, observed_result=evidence.summary, confidence_delta=0.15 if confirmed else -0.25,
    evidence_ids=[evidence.evidence_id], check_outcomes=checks, limitations=evidence.limitations,
  )
  return validation, result("validate_counterfactual", "ok", metrics=evidence.metrics, evidence=[evidence], limitations=evidence.limitations)
