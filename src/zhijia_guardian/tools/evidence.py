from __future__ import annotations

from itertools import count
from typing import Iterable

from zhijia_guardian.schema.models import ActionCandidate, DiagnosticCase, Evidence, Finding, Hypothesis, TimeRange, ToolResult, ValidationResult

_ids = count(1)


def create_evidence(kind: str, summary: str, source_tool: str, *, topic: str | None = None, time_window: TimeRange | None = None, metrics: dict | None = None,
                    limitations: list[str] | None = None, source_scope: str = "primary", source_dataset: str | None = None) -> Evidence:
  return Evidence(evidence_id=f"ev-{next(_ids):04d}", kind=kind, summary=summary, source_tool=source_tool, topic=topic, time_window=time_window,
                  metrics=metrics or {}, limitations=limitations or [], source_scope=source_scope, source_dataset=source_dataset)


def result(tool_name: str, status: str, *, metrics: dict | None = None, evidence: list[Evidence] | None = None, limitations: list[str] | None = None, time_window: TimeRange | None = None) -> ToolResult:
  return ToolResult(tool_name=tool_name, status=status, metrics=metrics or {}, evidence=evidence or [], limitations=limitations or [], time_window=time_window)


def validate_evidence_references(findings: Iterable[Finding], evidence: Iterable[Evidence]) -> list[str]:
  known = {item.evidence_id for item in evidence}
  return [f"{finding.finding_id} references unknown evidence {evidence_id}" for finding in findings for evidence_id in finding.evidence_ids if evidence_id not in known]


def rank_suspected_links(case: DiagnosticCase) -> list[Finding]:
  gaps = [e for e in case.evidence if e.kind in {"message_gap", "can_gap", "control_inconsistency"}]
  # Prefer the earliest direct message-gap evidence. A single transport outage can
  # generate several derivative CAN/control symptoms; do not report each as a new cause.
  direct = [e for e in gaps if e.kind == "message_gap"]
  selected = direct or gaps
  unique: dict[str, Evidence] = {}
  for evidence in selected:
    link = {"perceptionEvidence": "perceptionEvidence -> longitudinalPlan", "longitudinalPlan": "longitudinalPlan -> carControl", "sendcan": "carControl -> sendcan"}.get(evidence.topic, f"producer -> {evidence.topic or 'unknown'}")
    unique.setdefault(link, evidence)
  findings: list[Finding] = []
  for i, (link, evidence) in enumerate(unique.items(), 1):
    topic = evidence.topic or "unknown"
    findings.append(Finding(finding_id=f"finding-{i:03d}", classification="suspected_link", suspected_link=link,
                            statement=f"Observed anomaly on {topic}; this supports a suspected message/control-chain link, not a root cause.", confidence=0.7,
                            evidence_ids=[evidence.evidence_id], limitations=list(evidence.limitations)))
  if not findings and case.evidence:
    findings.append(Finding(finding_id="finding-001", classification="cannot_determine_root_cause", statement="No evidence supports a specific abnormal link in the observable topics.",
                            confidence=0.2, evidence_ids=[case.evidence[0].evidence_id], limitations=["absence of evidence is not evidence of absence"]))
  return findings


def formulate_hypotheses(case: DiagnosticCase) -> list[Hypothesis]:
  """Create testable mechanisms only from primary observed evidence."""
  hypotheses: list[Hypothesis] = []
  targets = {
    "perceptionEvidence": ("perceptionEvidence -> longitudinalPlan", "A perception-evidence publication interruption is the earliest observable fault mechanism in this case."),
    "longitudinalPlan": ("longitudinalPlan -> carControl", "A planner-output publication interruption is the earliest observable fault mechanism in this case."),
    "sendcan": ("carControl -> sendcan", "A sendcan transport/producer interruption is the earliest observable fault mechanism in this case."),
  }
  for evidence in case.evidence:
    if evidence.source_scope != "primary" or evidence.kind != "message_gap":
      continue
    if evidence.topic in targets:
      target_link, statement = targets[evidence.topic]
      hypothesis_id = f"hyp-{len(hypotheses) + 1:03d}"
      hypotheses.append(Hypothesis(hypothesis_id=hypothesis_id, target_link=target_link, statement=statement, status="proposed", confidence=0.65,
        evidence_ids=[evidence.evidence_id], expected_observation=f"Restoring missing {evidence.topic} publications removes its direct message gap.",
        next_action=f"counterfactual_repair_{evidence.topic}" if case.source.is_synthetic else "obtain aligned process logs or a controlled replay",
        rationale=f"A direct {evidence.topic} gap is primary observed evidence; downstream effects remain a hypothesis until tested."))
  return hypotheses


def rank_action_candidates(case: DiagnosticCase, hypotheses: list[Hypothesis]) -> list[ActionCandidate]:
  """Rank actions by explicit information-gain/cost, never hidden oracle labels."""
  upstream_priority = {"perceptionEvidence -> longitudinalPlan": 0.90, "longitudinalPlan -> carControl": 0.80, "carControl -> sendcan": 0.70}
  candidates = []
  for hypothesis in hypotheses:
    feasible = case.source.is_synthetic
    gain = upstream_priority.get(hypothesis.target_link, 0.50) if feasible else 0.25
    candidates.append(ActionCandidate(action_id=f"act-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id,
      action=hypothesis.next_action if feasible else "request_additional_observability", expected_information_gain=gain, estimated_cost=1.0 if feasible else 2.0,
      feasible=feasible, expected_discriminates=[hypothesis.target_link],
      rationale=("Controlled repair/replay directly tests whether the observed gap is mechanism-defining." if feasible else "Real logs cannot be modified; request aligned process/safety evidence instead.")))
  return candidates


def choose_highest_information_gain(candidates: list[ActionCandidate]) -> ActionCandidate | None:
  feasible = [candidate for candidate in candidates if candidate.feasible]
  pool = feasible or candidates
  return max(pool, key=lambda candidate: (candidate.expected_information_gain / candidate.estimated_cost, candidate.expected_information_gain), default=None)


def apply_validation_to_findings(case: DiagnosticCase, hypotheses: list[Hypothesis], validations: list[ValidationResult]) -> list[Finding]:
  findings = rank_suspected_links(case)
  confirmed = {item.hypothesis_id: item for item in validations if item.status == "confirmed"}
  if not case.source.is_synthetic:
    return findings
  for hypothesis in hypotheses:
    validation = confirmed.get(hypothesis.hypothesis_id)
    if validation:
      findings = [finding for finding in findings if finding.suspected_link != hypothesis.target_link]
      findings.insert(0, Finding(finding_id="finding-validated-001", classification="validated_root_cause", suspected_link=hypothesis.target_link,
        statement=f"Synthetic intervention validated the fault mechanism: {hypothesis.statement}", confidence=min(0.95, hypothesis.confidence + validation.confidence_delta),
        evidence_ids=[*hypothesis.evidence_ids, *validation.evidence_ids], limitations=["Validation applies to this synthetic/injected ADSLogRecord only; it does not prove a real vehicle incident root cause."]))
  return findings
