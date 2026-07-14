from __future__ import annotations

from zhijia_guardian.agents import CANAgent, CaseManagerAgent, ControlLinkAgent, CounterfactualAgent, EvidenceAuditorAgent, HypothesisAgent, MessageFlowAgent, ReportAgent, SafetyAgent, ValidationAgent
from zhijia_guardian.schema.models import AgentTraceEntry, AuxiliaryEvidenceBundle, DecisionBoard, Diagnosis, DiagnosticCase
from .state import DiagnosticWorkflowState
from .llm import resolve_llm_mode, select_specialists_with_llm


def _record(state: DiagnosticWorkflowState, agent, run) -> None:
  state.tool_results.extend(run.results)
  for tool_result in run.results:
    state.evidence.extend(tool_result.evidence)
  state.case.tool_results.extend(run.results)
  state.case.evidence = state.evidence
  state.tool_calls += len(run.results)
  state.completed_agents.append(agent.name)
  state.trace.append(AgentTraceEntry(step=len(state.trace) + 1, agent=agent.name, objective=agent.objective, hypothesis=run.hypothesis,
                                    tools_called=[item.tool_name for item in run.results], status="completed", output_summary=run.summary or run.stop_condition,
                                    evidence_ids=[e.evidence_id for item in run.results for e in item.evidence], stop_condition=run.stop_condition))


def run_diagnostic_workflow(case: DiagnosticCase, *, intervention_reference: DiagnosticCase | None = None, auxiliary_evidence: list[AuxiliaryEvidenceBundle] | None = None,
                            max_agent_rounds: int = 3, max_tool_calls: int = 30, routing_policy: str = "adaptive") -> tuple[Diagnosis, DiagnosticWorkflowState]:
  """Bounded active workflow; agents receive an oracle-free observed case only."""
  state = DiagnosticWorkflowState(case=case.observed_copy())
  state.case.auxiliary_evidence = list(auxiliary_evidence or [])
  manager = CaseManagerAgent()
  manager_run = manager.invoke(state.case)
  _record(state, manager, manager_run)
  state.available_topics = manager.private_state["topics"]
  state.requested_agents = manager.private_state["requested_agents"]
  mode = resolve_llm_mode()
  candidate_specialists, routing_note = select_specialists_with_llm(state.available_topics, manager.private_state["candidate_specialists"], mode)
  manager.private_state["requested_agents"] = state.requested_agents
  state.trace[-1].output_summary += f"; candidate routing: {routing_note}"
  state.active_hypotheses.append(manager_run.hypothesis or "")
  registry = {"message_flow": MessageFlowAgent(), "can": CANAgent(), "control_link": ControlLinkAgent(), "safety": SafetyAgent()}
  # Phase 1 always observes message flow. Follow-up specialists are selected from
  # its evidence rather than mechanically dispatching every available role.
  message_flow = registry["message_flow"]
  message_run = message_flow.invoke(state.case)
  _record(state, message_flow, message_run)
  gap_topics = {item.topic for item in state.evidence if item.source_scope == "primary" and item.kind == "message_gap" and item.topic}
  if routing_policy not in {"adaptive", "fixed"}:
    raise ValueError("routing_policy must be 'adaptive' or 'fixed'")
  if routing_policy == "fixed":
    follow_up = list(candidate_specialists)
  else:
    follow_up = []
    if "can" in candidate_specialists and gap_topics & {"can", "sendcan"}:
      follow_up.append("can")
    if "control_link" in candidate_specialists and gap_topics & {"longitudinalPlan", "carControl", "sendcan"}:
      follow_up.append("control_link")
    if "safety" in candidate_specialists and gap_topics & {"sendcan"}:
      follow_up.append("safety")
  state.requested_agents.extend(follow_up)
  state.trace[-1].output_summary += f"; {routing_policy} follow-up={follow_up or ['none']}"
  # A selected follow-up fan-out is one bounded round, not a fixed mandatory DAG.
  for name in follow_up:
    if state.tool_calls >= max_tool_calls:
      state.stop_reason = "maximum tool calls reached"
      break
    _record(state, registry[name], registry[name].invoke(state.case))
  state.iteration_count += 1
  # Round two actively chooses a falsification action. The optional clean synthetic
  # reference is available only inside a registered sandbox tool, never to agents.
  if state.iteration_count < max_agent_rounds and state.tool_calls < max_tool_calls:
    hypothesis_agent = HypothesisAgent()
    hypothesis_run = hypothesis_agent.invoke(state.case)
    _record(state, hypothesis_agent, hypothesis_run)
    state.hypotheses = hypothesis_run.hypotheses
    state.action_candidates = hypothesis_run.action_candidates
    state.decision_board = DecisionBoard(hypotheses=state.hypotheses, action_candidates=state.action_candidates,
      chosen_action_id=hypothesis_run.selected_action.action_id if hypothesis_run.selected_action else None,
      selection_rationale=hypothesis_run.summary)
    state.active_hypotheses = [item.statement for item in state.hypotheses]
    if state.hypotheses and state.tool_calls < max_tool_calls:
      intervention_agent = CounterfactualAgent()
      intervention_run = intervention_agent.invoke(state.case, state.hypotheses, hypothesis_run.selected_action, intervention_reference)
      _record(state, intervention_agent, intervention_run)
      state.interventions = intervention_run.interventions
      if state.interventions and state.tool_calls < max_tool_calls:
        validation_agent = ValidationAgent()
        validation_run = validation_agent.invoke(state.hypotheses, state.interventions, intervention_run.counterfactual_cases)
        _record(state, validation_agent, validation_run)
        state.validations = validation_run.validations
    state.iteration_count += 1
  auditor = EvidenceAuditorAgent()
  audit = auditor.invoke(state.case, state.hypotheses, state.validations)
  state.audit_result = audit
  state.findings = audit.allowed_findings
  state.trace.append(AgentTraceEntry(step=len(state.trace) + 1, agent=auditor.name, objective=auditor.objective, tools_called=["validate_evidence_references", "rank_suspected_links"], status=audit.status,
                                    output_summary=f"audit issues={len(audit.issues)}, allowed_findings={len(audit.allowed_findings)}", evidence_ids=[e.evidence_id for e in state.case.evidence], stop_condition="audited all proposed findings"))
  state.stop_reason = state.stop_reason or "observational and active-validation rounds completed"
  limitations = ["Agent conclusions are limited to logged, observable topics.", "No agent reads synthetic oracle or injected-fault manifest.", "A counterfactually supported injected fault location is permitted only for controlled synthetic replays, never a real route.", "Synthetic repair controls do not establish a real-world root cause or an unobserved propagation mechanism."]
  limitations.extend(issue for issue in audit.issues)
  state.case.findings = state.findings
  state.case.hypotheses = [item.model_dump() for item in state.hypotheses]
  state.case.limitations = limitations
  reporter = ReportAgent()
  state.completed_agents.append(reporter.name)
  state.trace.append(AgentTraceEntry(step=len(state.trace) + 1, agent=reporter.name, objective=reporter.objective, tools_called=["render_diagnosis_report"], status="completed",
                                    output_summary="Structured audited state passed to artifact renderer; no upstream facts added.", evidence_ids=[e.evidence_id for e in state.case.evidence], stop_condition="artifact rendering delegated"))
  return Diagnosis(case_id=state.case.case_id, source=state.case.source, findings=state.findings, limitations=limitations, audit=audit,
                   hypotheses=state.hypotheses, interventions=state.interventions, validations=state.validations, decision_board=state.decision_board, stop_reason=state.stop_reason), state
