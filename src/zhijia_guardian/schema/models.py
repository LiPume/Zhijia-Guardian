from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceInfo(BaseModel):
  stack: str = "openpilot-like"
  dataset: str
  route_id: str | None = None
  segment_id: str | None = None
  source_path: str | None = None
  is_synthetic: bool = False


class TimeRange(BaseModel):
  start_ns: int
  end_ns: int

  @property
  def duration_s(self) -> float:
    return max(0.0, (self.end_ns - self.start_ns) / 1e9)


class ADSMessage(BaseModel):
  topic: str
  mono_time: int = Field(ge=0)
  sequence: int = Field(ge=0)
  payload_summary: dict[str, Any] = Field(default_factory=dict)
  raw_reference: str | None = None
  quality_flags: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
  evidence_id: str
  kind: str
  summary: str
  topic: str | None = None
  time_window: TimeRange | None = None
  metrics: dict[str, Any] = Field(default_factory=dict)
  source_tool: str
  source_scope: Literal["primary", "auxiliary", "validation"] = "primary"
  source_dataset: str | None = None
  limitations: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
  tool_name: str
  status: Literal["ok", "insufficient_observability", "error"]
  time_window: TimeRange | None = None
  metrics: dict[str, Any] = Field(default_factory=dict)
  evidence: list[Evidence] = Field(default_factory=list)
  limitations: list[str] = Field(default_factory=list)


class Finding(BaseModel):
  finding_id: str
  classification: Literal["suspected_link", "validated_root_cause", "insufficient_evidence", "cannot_determine_root_cause"]
  suspected_link: str | None = None
  statement: str
  confidence: float = Field(ge=0, le=1)
  evidence_ids: list[str] = Field(min_length=1)
  limitations: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
  hypothesis_id: str
  target_link: str
  statement: str
  status: Literal["proposed", "supported", "refuted", "insufficient_evidence"] = "proposed"
  confidence: float = Field(ge=0, le=1)
  evidence_ids: list[str] = Field(min_length=1)
  expected_observation: str
  next_action: str
  rationale: str


class Intervention(BaseModel):
  intervention_id: str
  hypothesis_id: str
  action: str
  target_link: str
  feasible: bool
  status: Literal["executed", "not_feasible", "error"]
  rationale: str
  evidence_ids: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
  validation_id: str
  hypothesis_id: str
  status: Literal["confirmed", "refuted", "insufficient_evidence"]
  expected_observation: str
  observed_result: str
  confidence_delta: float = Field(ge=-1, le=1)
  evidence_ids: list[str] = Field(min_length=1)


class AuxiliaryEvidenceBundle(BaseModel):
  bundle_id: str
  source_dataset: Literal["nuscenes", "nuplan"]
  role: Literal["perception_evidence_adapter", "planning_evidence_adapter"]
  same_route_as_primary: bool = False
  source_reference: str | None = None
  evidence: list[Evidence] = Field(default_factory=list)
  limitations: list[str] = Field(default_factory=list)


class DiagnosticCase(BaseModel):
  model_config = ConfigDict(validate_assignment=True)
  case_id: str
  source: SourceInfo
  time_range: TimeRange
  service_catalog: dict[str, Any] = Field(default_factory=dict)
  messages: list[ADSMessage] = Field(default_factory=list)
  dependency_graph: dict[str, list[str]] = Field(default_factory=dict)
  observations: list[dict[str, Any]] = Field(default_factory=list)
  auxiliary_evidence: list[AuxiliaryEvidenceBundle] = Field(default_factory=list)
  hypotheses: list[dict[str, Any]] = Field(default_factory=list)
  tool_results: list[ToolResult] = Field(default_factory=list)
  evidence: list[Evidence] = Field(default_factory=list)
  findings: list[Finding] = Field(default_factory=list)
  limitations: list[str] = Field(default_factory=list)
  oracle: dict[str, Any] | None = None

  @model_validator(mode="after")
  def message_times_in_range(self) -> "DiagnosticCase":
    for msg in self.messages:
      if not self.time_range.start_ns <= msg.mono_time <= self.time_range.end_ns:
        raise ValueError(f"message {msg.topic} is outside case time range")
    return self

  def observed_copy(self) -> "DiagnosticCase":
    """Return the only view supplied to agents; evaluator-only oracle is removed."""
    return self.model_copy(deep=True, update={"oracle": None})


class AgentTraceEntry(BaseModel):
  step: int
  agent: str
  objective: str
  hypothesis: str | None = None
  tools_called: list[str] = Field(default_factory=list)
  status: str
  output_summary: str
  evidence_ids: list[str] = Field(default_factory=list)
  stop_condition: str | None = None


class AuditResult(BaseModel):
  status: Literal["passed", "downgraded", "failed"]
  issues: list[str] = Field(default_factory=list)
  allowed_findings: list[Finding] = Field(default_factory=list)


class Diagnosis(BaseModel):
  case_id: str
  source: SourceInfo
  findings: list[Finding]
  limitations: list[str]
  audit: AuditResult
  hypotheses: list[Hypothesis] = Field(default_factory=list)
  interventions: list[Intervention] = Field(default_factory=list)
  validations: list[ValidationResult] = Field(default_factory=list)
  stop_reason: str
  agent_trace_path: str | None = None


def write_json(model: BaseModel | dict[str, Any], path: Path) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  content = model.model_dump_json(indent=2) if isinstance(model, BaseModel) else __import__("json").dumps(model, indent=2)
  path.write_text(content + "\n", encoding="utf-8")
