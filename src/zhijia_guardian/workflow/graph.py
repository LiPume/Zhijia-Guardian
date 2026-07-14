from __future__ import annotations

from zhijia_guardian.agents import CANAgent, CaseManagerAgent, ControlLinkAgent, EvidenceAuditorAgent, MessageFlowAgent, ReportAgent, SafetyAgent
from zhijia_guardian.schema.models import AgentTraceEntry, Diagnosis, DiagnosticCase
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


def run_diagnostic_workflow(case: DiagnosticCase, *, max_agent_rounds: int = 3, max_tool_calls: int = 20) -> tuple[Diagnosis, DiagnosticWorkflowState]:
  """Explicit bounded tool-use workflow. Agents receive an oracle-free copy only."""
  state = DiagnosticWorkflowState(case=case.observed_copy())
  manager = CaseManagerAgent()
  manager_run = manager.invoke(state.case)
  _record(state, manager, manager_run)
  state.available_topics = manager.private_state["topics"]
  state.requested_agents = manager.private_state["requested_agents"]
  mode = resolve_llm_mode()
  state.requested_agents, routing_note = select_specialists_with_llm(state.available_topics, state.requested_agents, mode)
  manager.private_state["requested_agents"] = state.requested_agents
  state.trace[-1].output_summary += f"; {routing_note}"
  state.active_hypotheses.append(manager_run.hypothesis or "")
  registry = {"message_flow": MessageFlowAgent(), "can": CANAgent(), "control_link": ControlLinkAgent(), "safety": SafetyAgent()}
  # A dispatch fan-out is one agent round. Specialists within it are not artificial
  # sequential rounds; this keeps the configured bound meaningful.
  for name in state.requested_agents:
    if state.iteration_count >= max_agent_rounds or state.tool_calls >= max_tool_calls:
      state.stop_reason = "maximum agent rounds or tool calls reached"
      break
    agent = registry[name]
    run = agent.invoke(state.case)
    _record(state, agent, run)
  state.iteration_count += 1
  auditor = EvidenceAuditorAgent()
  audit = auditor.invoke(state.case)
  state.audit_result = audit
  state.findings = audit.allowed_findings
  state.trace.append(AgentTraceEntry(step=len(state.trace) + 1, agent=auditor.name, objective=auditor.objective, tools_called=["validate_evidence_references", "rank_suspected_links"], status=audit.status,
                                    output_summary=f"audit issues={len(audit.issues)}, allowed_findings={len(audit.allowed_findings)}", evidence_ids=[e.evidence_id for e in state.case.evidence], stop_condition="audited all proposed findings"))
  state.stop_reason = state.stop_reason or "all dispatched specialists and evidence audit completed"
  limitations = ["Agent conclusions are limited to logged, observable topics.", "No agent reads synthetic oracle or injected-fault manifest."]
  limitations.extend(issue for issue in audit.issues)
  state.case.findings = state.findings
  state.case.limitations = limitations
  reporter = ReportAgent()
  state.completed_agents.append(reporter.name)
  state.trace.append(AgentTraceEntry(step=len(state.trace) + 1, agent=reporter.name, objective=reporter.objective, tools_called=["render_diagnosis_report"], status="completed",
                                    output_summary="Structured audited state passed to artifact renderer; no upstream facts added.", evidence_ids=[e.evidence_id for e in state.case.evidence], stop_condition="artifact rendering delegated"))
  return Diagnosis(case_id=state.case.case_id, source=state.case.source, findings=state.findings, limitations=limitations, audit=audit, stop_reason=state.stop_reason), state
