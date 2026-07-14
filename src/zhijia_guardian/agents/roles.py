from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from zhijia_guardian.schema.models import ActionCandidate, AuditResult, DiagnosticCase, Finding, Hypothesis, Intervention, ToolResult, ValidationResult
from zhijia_guardian.tools import (build_message_dependency_graph, calculate_can_address_frequency, calculate_topic_frequency, check_carcontrol_sendcan_consistency,
  check_control_command_response, check_sendcan_vehicle_state_consistency, detect_can_gaps, detect_message_gaps, detect_stale_messages, detect_timestamp_discontinuity,
  apply_validation_to_findings, choose_highest_priority, extract_onroad_events, extract_panda_safety_events, formulate_hypotheses, list_available_topics, rank_action_candidates,
  run_counterfactual_repair, summarize_can_addresses, validate_counterfactual, validate_evidence_references)


@dataclass
class AgentRun:
  results: list[ToolResult] = field(default_factory=list)
  hypothesis: str | None = None
  summary: str = ""
  stop_condition: str = "tools completed"
  hypotheses: list[Hypothesis] = field(default_factory=list)
  interventions: list[Intervention] = field(default_factory=list)
  validations: list[ValidationResult] = field(default_factory=list)
  counterfactual_cases: dict[str, DiagnosticCase | None] = field(default_factory=dict)
  action_candidates: list[ActionCandidate] = field(default_factory=list)
  selected_action: ActionCandidate | None = None


@dataclass
class ToolUserAgent:
  name: str
  objective: str
  tools: dict[str, Callable]
  private_state: dict = field(default_factory=dict)

  def invoke(self, case: DiagnosticCase) -> AgentRun:
    raise NotImplementedError


class CaseManagerAgent(ToolUserAgent):
  def __init__(self):
    super().__init__("case_manager", "Inventory observable services, choose specialist agents, and keep hypotheses bounded.", {"list_available_topics": list_available_topics, "build_message_dependency_graph": build_message_dependency_graph})

  def invoke(self, case: DiagnosticCase) -> AgentRun:
    catalog, graph = self.tools["list_available_topics"](case), self.tools["build_message_dependency_graph"](case)
    topics = set(catalog.metrics["topics"])
    candidates = []
    if topics & {"can", "sendcan"}: candidates.append("can")
    if topics & {"carControl", "sendcan", "carState", "controlsState"}: candidates.append("control_link")
    if topics & {"pandaStates", "onroadEvents"}: candidates.append("safety")
    self.private_state = {"requested_agents": ["message_flow"], "candidate_specialists": candidates, "topics": sorted(topics)}
    return AgentRun([catalog, graph], "Start with message-flow facts; follow-up specialists are selected only when evidence makes them discriminative.", f"initial_dispatch=['message_flow']; candidates={candidates}")


class MessageFlowAgent(ToolUserAgent):
  def __init__(self):
    super().__init__("message_flow_agent", "Test message frequency, gaps, timestamp order, and staleness.", {})

  def invoke(self, case: DiagnosticCase) -> AgentRun:
    topics = [topic for topic in ("modelV2", "longitudinalPlan", "carControl", "sendcan") if any(m.topic == topic for m in case.messages)]
    results = [calculate_topic_frequency(case), detect_timestamp_discontinuity(case)]
    for topic in topics:
      results.extend([detect_message_gaps(case, topic), detect_stale_messages(case, topic)])
    return AgentRun(results, "A producer/consumer topic may have a gap or stale publication.", "all observable topics checked")


class CANAgent(ToolUserAgent):
  def __init__(self): super().__init__("can_diagnostic_agent", "Inspect CAN/sendcan frame coverage and timing.", {})
  def invoke(self, case: DiagnosticCase) -> AgentRun:
    topics = [topic for topic in ("can", "sendcan") if any(m.topic == topic for m in case.messages)]
    if not topics: return AgentRun([], "CAN unavailable", "insufficient_observability")
    results = [item for topic in topics for item in (summarize_can_addresses(case, topic), calculate_can_address_frequency(case, topic), detect_can_gaps(case, topic))]
    return AgentRun(results, "CAN transport may exhibit a gap or address-level anomaly.", "all available CAN topics checked")


class ControlLinkAgent(ToolUserAgent):
  def __init__(self): super().__init__("control_link_agent", "Check planner/control/sendcan/carState consistency without inventing missing signals.", {})
  def invoke(self, case: DiagnosticCase) -> AgentRun:
    return AgentRun([check_control_command_response(case), check_carcontrol_sendcan_consistency(case), check_sendcan_vehicle_state_consistency(case)], "A first control-chain divergence may be observable.", "control consistency checks completed")


class SafetyAgent(ToolUserAgent):
  def __init__(self): super().__init__("safety_vehicle_interface_agent", "Inspect panda safety and onroad event evidence.", {})
  def invoke(self, case: DiagnosticCase) -> AgentRun:
    return AgentRun([extract_panda_safety_events(case), extract_onroad_events(case)], "Safety-layer blocking or events may explain a downstream symptom.", "safety topics checked")


class HypothesisAgent(ToolUserAgent):
  def __init__(self): super().__init__("hypothesis_investigation_agent", "Generate competing, falsifiable explanations and rank the next discriminative action.", {"formulate_hypotheses": formulate_hypotheses, "rank_action_candidates": rank_action_candidates, "choose_highest_priority": choose_highest_priority})
  def invoke(self, case: DiagnosticCase) -> AgentRun:
    hypotheses = self.tools["formulate_hypotheses"](case)
    if not hypotheses:
      return AgentRun(hypothesis="No testable primary-evidence hypothesis is available.", summary="No intervention is selected without a supported primary mechanism.", stop_condition="insufficient evidence")
    candidates = self.tools["rank_action_candidates"](case, hypotheses)
    selected = self.tools["choose_highest_priority"](candidates)
    self.private_state = {"hypotheses": hypotheses, "candidates": candidates, "selected": selected}
    return AgentRun(hypothesis=selected.rationale if selected else hypotheses[0].statement, hypotheses=hypotheses, action_candidates=candidates, selected_action=selected,
      summary=f"Formulated {len(hypotheses)} competing hypotheses; selected {selected.action_id if selected else 'no action'} by observable diagnostic-priority score.", stop_condition="decision board ranked")


class CounterfactualAgent(ToolUserAgent):
  def __init__(self): super().__init__("counterfactual_executor", "Execute named targeted, sham, and alternative synthetic controls selected by the investigation agent.", {"run_counterfactual_repair": run_counterfactual_repair})
  def invoke(self, case: DiagnosticCase, hypotheses: list[Hypothesis], selected_action: ActionCandidate | None, reference: DiagnosticCase | None = None) -> AgentRun:
    if not hypotheses or selected_action is None:
      return AgentRun(summary="No hypothesis available for intervention.", stop_condition="no action")
    hypothesis = next(item for item in hypotheses if item.hypothesis_id == selected_action.hypothesis_id)
    interventions, results, replays = [], [], {}
    for role in ("targeted_repair", "sham_repair", "alternative_repair"):
      intervention, tool_result, repaired = self.tools["run_counterfactual_repair"](case, reference, hypothesis, role=role)
      interventions.append(intervention)
      results.append(tool_result)
      replays[role] = repaired
    return AgentRun(results, hypothesis=hypothesis.statement, interventions=interventions, counterfactual_cases=replays,
      summary="Executed targeted, sham, and alternative controls." if interventions[0].feasible else interventions[0].rationale, stop_condition="counterfactual controls completed or rejected")


class ValidationAgent(ToolUserAgent):
  def __init__(self): super().__init__("validation_tool", "Compare pre-registered targeted and control replay outcomes.", {"validate_counterfactual": validate_counterfactual})
  def invoke(self, hypotheses: list[Hypothesis], interventions: list[Intervention], replays: dict[str, DiagnosticCase | None]) -> AgentRun:
    if not hypotheses or not interventions:
      return AgentRun(summary="No intervention result to validate.", stop_condition="no validation")
    hypothesis = next(item for item in hypotheses if item.hypothesis_id == interventions[0].hypothesis_id)
    validation, tool_result = self.tools["validate_counterfactual"](hypothesis, replays, interventions)
    return AgentRun([tool_result], hypothesis=hypothesis.statement, validations=[validation], summary=f"Validation {validation.status}.", stop_condition="prediction compared with replay")


class EvidenceAuditorAgent(ToolUserAgent):
  def __init__(self): super().__init__("evidence_auditor", "Reject claims without valid evidence and downgrade unobservable root-cause claims.", {})
  def invoke(self, case: DiagnosticCase, hypotheses: list[Hypothesis] | None = None, validations: list[ValidationResult] | None = None) -> AuditResult:
    proposed = apply_validation_to_findings(case, hypotheses or [], validations or [])
    all_evidence = [*case.evidence, *(evidence for bundle in case.auxiliary_evidence for evidence in bundle.evidence)]
    issues = validate_evidence_references(proposed, all_evidence)
    if case.auxiliary_evidence:
      issues.extend(f"{bundle.source_dataset} auxiliary evidence is not treated as a shared physical route with {case.source.dataset}." for bundle in case.auxiliary_evidence)
    allowed: list[Finding] = []
    for finding in proposed:
      if finding.classification == "counterfactually_supported_injected_fault_location" and not case.source.is_synthetic:
        issues.append(f"{finding.finding_id} attempted synthetic-only counterfactual language on a real case")
      elif not finding.evidence_ids:
        issues.append(f"{finding.finding_id} lacks evidence")
      else:
        allowed.append(finding)
    status = "failed" if not allowed else "downgraded" if issues else "passed"
    return AuditResult(status=status, issues=issues, allowed_findings=allowed)


class ReportAgent(ToolUserAgent):
  def __init__(self): super().__init__("report_renderer", "Render only audited structured diagnosis state.", {})
