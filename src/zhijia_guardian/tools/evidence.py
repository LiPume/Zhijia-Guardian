from __future__ import annotations

from itertools import count
from typing import Iterable

from zhijia_guardian.schema.models import ActionCandidate, DiagnosticCase, Evidence, Finding, Hypothesis, TimeRange, ToolResult, ValidationResult

_ids = count(1)

_TOPIC_TO_LINK = {
  "modelV2": "modelV2 -> longitudinalPlan",
  "longitudinalPlan": "longitudinalPlan -> carControl",
  "sendcan": "carControl -> sendcan",
}


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
  gaps = [item for item in case.evidence if item.source_scope == "primary" and item.kind in {"message_gap", "can_gap", "control_inconsistency"}]
  direct = [item for item in gaps if item.kind == "message_gap"]
  selected = direct or gaps
  unique: dict[str, Evidence] = {}
  for evidence in selected:
    link = _TOPIC_TO_LINK.get(evidence.topic or "", f"producer -> {evidence.topic or 'unknown'}")
    unique.setdefault(link, evidence)
  findings: list[Finding] = []
  for index, (link, evidence) in enumerate(unique.items(), 1):
    topic = evidence.topic or "unknown"
    findings.append(Finding(
      finding_id=f"finding-{index:03d}", classification="suspected_link", suspected_link=link,
      statement=f"Observed anomaly on {topic}; this supports a suspected message/control-chain link, not a root cause.", confidence=0.7,
      evidence_ids=[evidence.evidence_id], limitations=list(evidence.limitations),
    ))
  if not findings and case.evidence:
    findings.append(Finding(
      finding_id="finding-001", classification="cannot_determine_root_cause",
      statement="No evidence supports a specific abnormal link in the observable topics.", confidence=0.2,
      evidence_ids=[case.evidence[0].evidence_id], limitations=["absence of evidence is not evidence of absence"],
    ))
  return findings


def _gap_evidence(case: DiagnosticCase) -> list[Evidence]:
  return [item for item in case.evidence if item.source_scope == "primary" and item.kind == "message_gap" and item.topic in _TOPIC_TO_LINK]


def formulate_hypotheses(case: DiagnosticCase) -> list[Hypothesis]:
  """Generate explicit competing explanations from observed primary evidence only."""
  direct = _gap_evidence(case)
  hypotheses: list[Hypothesis] = []
  for evidence in direct:
    topic = evidence.topic or ""
    link = _TOPIC_TO_LINK[topic]
    hypotheses.append(Hypothesis(
      hypothesis_id=f"hyp-{len(hypotheses) + 1:03d}", hypothesis_type="propagation", target_link=link,
      statement=f"A {topic} publication interruption is an observable fault location whose effects may propagate along {link}.",
      status="proposed", confidence=0.65, evidence_ids=[evidence.evidence_id],
      expected_observation=f"Targeted repair of {topic} removes its direct gap while sham and alternative repairs do not.",
      next_action=f"counterfactual_repair_{topic}" if case.source.is_synthetic else "obtain aligned process logs or a controlled replay",
      rationale=f"A direct {topic} gap is primary observed evidence. Propagation is not assumed until a pre-registered downstream prediction is observed.",
    ))
  if len(direct) >= 2:
    topics = [item.topic or "unknown" for item in direct]
    evidence_ids = [item.evidence_id for item in direct]
    hypotheses.append(Hypothesis(
      hypothesis_id=f"hyp-{len(hypotheses) + 1:03d}", hypothesis_type="independent_fault", target_link=" || ".join(topics),
      statement=f"The gaps on {', '.join(topics)} are independent faults rather than one propagation chain.", status="proposed", confidence=0.25,
      evidence_ids=evidence_ids, expected_observation="Repairing one topic leaves the other direct gap unchanged.",
      next_action="compare_targeted_repairs", rationale="Multiple direct gaps may be independent; upstream ordering alone is not sufficient evidence.",
    ))
    hypotheses.append(Hypothesis(
      hypothesis_id=f"hyp-{len(hypotheses) + 1:03d}", hypothesis_type="common_cause", target_link=f"unobserved_common_cause -> {{{', '.join(topics)}}}",
      statement=f"An unobserved common cause could jointly affect {', '.join(topics)}.", status="insufficient_evidence", confidence=0.15,
      evidence_ids=evidence_ids, expected_observation="Aligned process, safety, or transport telemetry would reveal a shared precursor.",
      next_action="request_common_cause_observability", rationale="The current message view cannot distinguish a hidden common cause from coincident direct failures.",
    ))
    hypotheses.append(Hypothesis(
      hypothesis_id=f"hyp-{len(hypotheses) + 1:03d}", hypothesis_type="insufficient_observability", target_link="observability_gap",
      statement="The current topic set may be insufficient to distinguish propagation, independent faults, and a hidden common cause.", status="insufficient_evidence", confidence=0.20,
      evidence_ids=evidence_ids, expected_observation="An aligned process/safety/transport trace changes the posterior over the competing explanations.",
      next_action="request_discriminative_observability", rationale="This explicit abstention hypothesis prevents an apparent upstream ordering from being treated as proof of one cause.",
    ))
  return hypotheses


def _downstream_count(graph: dict[str, list[str]], topic: str) -> int:
  seen, frontier = set(), list(graph.get(topic, []))
  while frontier:
    node = frontier.pop()
    if node in seen:
      continue
    seen.add(node)
    frontier.extend(graph.get(node, []))
  return len(seen)


def _evidence_strength(hypothesis: Hypothesis, evidence_by_id: dict[str, Evidence]) -> float:
  values = []
  for evidence_id in hypothesis.evidence_ids:
    metrics = evidence_by_id[evidence_id].metrics
    median_s, gap_s = float(metrics.get("median_s", 0.0)), float(metrics.get("gap_s", 0.0))
    ratio = gap_s / median_s if median_s > 0 else 0.0
    values.append(min(1.0, ratio / 8.0))
  return round(sum(values) / len(values), 3) if values else 0.0


def rank_action_candidates(case: DiagnosticCase, hypotheses: list[Hypothesis]) -> list[ActionCandidate]:
  """Use an observable diagnostic-priority score, not uncalibrated information gain."""
  evidence_by_id = {item.evidence_id: item for item in case.evidence}
  max_reach = max((len(case.dependency_graph) - 1), 1)
  candidates: list[ActionCandidate] = []
  for hypothesis in hypotheses:
    topic = next((source for source, link in _TOPIC_TO_LINK.items() if link == hypothesis.target_link), None)
    feasible = bool(case.source.is_synthetic and topic)
    if feasible:
      components = {
        "evidence_strength": _evidence_strength(hypothesis, evidence_by_id),
        "downstream_explanatory_coverage": round(_downstream_count(case.dependency_graph, topic) / max_reach, 3),
        "discriminability": round(1.0 / max(1, len(hypotheses)), 3),
        "feasibility": 1.0,
      }
      cost = 1.0
      score = round((components["evidence_strength"] * components["downstream_explanatory_coverage"] * components["discriminability"] * components["feasibility"]) / cost, 3)
      action, rationale = hypothesis.next_action, "Score is evidence strength × reachable downstream coverage × competing-hypothesis discriminability × feasibility / cost."
    else:
      components, cost, score = {"evidence_strength": _evidence_strength(hypothesis, evidence_by_id), "downstream_explanatory_coverage": 0.0, "discriminability": 0.0, "feasibility": 0.0}, 2.0, 0.0
      action, rationale = "request_additional_observability", "No registered synthetic repair is feasible; request data that can distinguish this explanation."
    candidates.append(ActionCandidate(
      action_id=f"act-{hypothesis.hypothesis_id}", hypothesis_id=hypothesis.hypothesis_id, action=action,
      diagnostic_priority_score=score, estimated_cost=cost, feasible=feasible,
      expected_discriminates=["propagation", "independent_fault", "common_cause"] if feasible else [hypothesis.hypothesis_type],
      score_components=components, rationale=rationale,
    ))
  return candidates


def choose_highest_priority(candidates: list[ActionCandidate]) -> ActionCandidate | None:
  feasible = [item for item in candidates if item.feasible]
  pool = feasible or candidates
  return max(pool, key=lambda item: (item.diagnostic_priority_score / item.estimated_cost, item.diagnostic_priority_score), default=None)


def apply_validation_to_findings(case: DiagnosticCase, hypotheses: list[Hypothesis], validations: list[ValidationResult]) -> list[Finding]:
  findings = rank_suspected_links(case)
  confirmed = {item.hypothesis_id: item for item in validations if item.status == "confirmed"}
  if not case.source.is_synthetic:
    return findings
  for hypothesis in hypotheses:
    validation = confirmed.get(hypothesis.hypothesis_id)
    required_controls = {"targeted_direct_gap_removed", "sham_preserved_target_gap", "alternative_preserved_target_gap"}
    if hypothesis.hypothesis_type != "propagation" or validation is None or not required_controls <= {key for key, passed in validation.check_outcomes.items() if passed}:
      continue
    findings = [item for item in findings if item.suspected_link != hypothesis.target_link]
    findings.insert(0, Finding(
      finding_id="finding-counterfactually-supported-001", classification="counterfactually_supported_injected_fault_location", suspected_link=hypothesis.target_link,
      statement=f"Synthetic controls support the injected fault location on {hypothesis.target_link}; this does not establish a real-world root cause or an unobserved propagation mechanism.",
      confidence=min(0.9, hypothesis.confidence + validation.confidence_delta), evidence_ids=[*hypothesis.evidence_ids, *validation.evidence_ids],
      limitations=["Only a controlled synthetic fault location is supported.", "No downstream propagation claim is made unless a separate downstream prediction is observed."],
    ))
  return findings
