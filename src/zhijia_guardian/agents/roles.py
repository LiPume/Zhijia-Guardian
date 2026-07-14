from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from zhijia_guardian.schema.models import AuditResult, DiagnosticCase, Finding, Hypothesis, Intervention, ToolResult, ValidationResult
from zhijia_guardian.tools import (build_message_dependency_graph, calculate_can_address_frequency, calculate_topic_frequency, check_carcontrol_sendcan_consistency,
  check_control_command_response, check_sendcan_vehicle_state_consistency, detect_can_gaps, detect_message_gaps, detect_stale_messages, detect_timestamp_discontinuity,
  apply_validation_to_findings, extract_onroad_events, extract_panda_safety_events, formulate_hypotheses, list_available_topics, run_counterfactual_repair, summarize_can_addresses,
  validate_counterfactual, validate_evidence_references)


@dataclass
class AgentRun:
  results: list[ToolResult] = field(default_factory=list)
  hypothesis: str | None = None
  summary: str = ""
  stop_condition: str = "tools completed"
  hypotheses: list[Hypothesis] = field(default_factory=list)
  interventions: list[Intervention] = field(default_factory=list)
  validations: list[ValidationResult] = field(default_factory=list)
  counterfactual_case: DiagnosticCase | None = None


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
    requested = ["message_flow"]
    if topics & {"can", "sendcan"}: requested.append("can")
    if topics & {"carControl", "sendcan", "carState", "controlsState"}: requested.append("control_link")
    if topics & {"pandaStates", "onroadEvents"}: requested.append("safety")
    self.private_state = {"requested_agents": requested, "topics": sorted(topics)}
    return AgentRun([catalog, graph], "An abnormal message/control link may be observable; specialist checks are required.", f"dispatch={requested}")


class MessageFlowAgent(ToolUserAgent):
  def __init__(self):
    super().__init__("message_flow_agent", "Test message frequency, gaps, timestamp order, and staleness.", {})

  def invoke(self, case: DiagnosticCase) -> AgentRun:
    topics = [topic for topic in ("perceptionEvidence", "longitudinalPlan", "carControl", "sendcan") if any(m.topic == topic for m in case.messages)]
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
  def __init__(self): super().__init__("hypothesis_agent", "Convert primary evidence into competing, falsifiable fault-mechanism hypotheses.", {"formulate_hypotheses": formulate_hypotheses})
  def invoke(self, case: DiagnosticCase) -> AgentRun:
    hypotheses = self.tools["formulate_hypotheses"](case)
    if not hypotheses:
      return AgentRun(hypothesis="No testable primary-evidence hypothesis is available.", summary="No intervention is selected without a supported primary mechanism.", stop_condition="insufficient evidence")
    self.private_state["hypotheses"] = hypotheses
    return AgentRun(hypothesis=hypotheses[0].statement, hypotheses=hypotheses, summary=f"Formulated {len(hypotheses)} falsifiable hypothesis(es).", stop_condition="highest-information action selected")


class CounterfactualAgent(ToolUserAgent):
  def __init__(self): super().__init__("counterfactual_intervention_agent", "Choose and execute only feasible synthetic repair/replay interventions.", {"run_counterfactual_repair": run_counterfactual_repair})
  def invoke(self, case: DiagnosticCase, hypotheses: list[Hypothesis], reference: DiagnosticCase | None = None) -> AgentRun:
    if not hypotheses:
      return AgentRun(summary="No hypothesis available for intervention.", stop_condition="no action")
    intervention, tool_result, repaired = self.tools["run_counterfactual_repair"](case, reference, hypotheses[0])
    return AgentRun([tool_result], hypothesis=hypotheses[0].statement, interventions=[intervention], counterfactual_case=repaired,
      summary=f"{intervention.status}: {intervention.action}", stop_condition="counterfactual action completed or rejected")


class ValidationAgent(ToolUserAgent):
  def __init__(self): super().__init__("validation_agent", "Compare expected and observed counterfactual effects and update hypothesis confidence.", {"validate_counterfactual": validate_counterfactual})
  def invoke(self, hypotheses: list[Hypothesis], intervention: Intervention | None, repaired: DiagnosticCase | None) -> AgentRun:
    if not hypotheses or intervention is None:
      return AgentRun(summary="No intervention result to validate.", stop_condition="no validation")
    validation, tool_result = self.tools["validate_counterfactual"](hypotheses[0], repaired, intervention)
    return AgentRun([tool_result], hypothesis=hypotheses[0].statement, validations=[validation], summary=f"Validation {validation.status}.", stop_condition="prediction compared with replay")


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
      if finding.classification == "validated_root_cause" and not case.source.is_synthetic:
        issues.append(f"{finding.finding_id} attempted real-case validated-root-cause language")
      elif not finding.evidence_ids:
        issues.append(f"{finding.finding_id} lacks evidence")
      else:
        allowed.append(finding)
    status = "failed" if not allowed else "downgraded" if issues else "passed"
    return AuditResult(status=status, issues=issues, allowed_findings=allowed)


class ReportAgent(ToolUserAgent):
  def __init__(self): super().__init__("report_agent", "Render only audited structured diagnosis state.", {})
