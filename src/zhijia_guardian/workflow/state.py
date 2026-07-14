from dataclasses import dataclass, field

from zhijia_guardian.schema.models import ActionCandidate, AgentTraceEntry, AuditResult, DecisionBoard, DiagnosticCase, Hypothesis, Intervention, ToolResult, ValidationResult


@dataclass
class DiagnosticWorkflowState:
  case: DiagnosticCase
  available_topics: list[str] = field(default_factory=list)
  active_hypotheses: list[str] = field(default_factory=list)
  hypotheses: list[Hypothesis] = field(default_factory=list)
  interventions: list[Intervention] = field(default_factory=list)
  validations: list[ValidationResult] = field(default_factory=list)
  action_candidates: list[ActionCandidate] = field(default_factory=list)
  decision_board: DecisionBoard | None = None
  requested_agents: list[str] = field(default_factory=list)
  completed_agents: list[str] = field(default_factory=list)
  tool_results: list[ToolResult] = field(default_factory=list)
  evidence: list = field(default_factory=list)
  findings: list = field(default_factory=list)
  audit_result: AuditResult | None = None
  trace: list[AgentTraceEntry] = field(default_factory=list)
  iteration_count: int = 0
  tool_calls: int = 0
  stop_reason: str | None = None
