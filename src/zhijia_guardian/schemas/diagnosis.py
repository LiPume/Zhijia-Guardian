from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceRecord(StrictModel):
    evidence_id: str
    metric_name: str
    value: float | bool | str | None = None
    threshold: float | None = None
    time: float | None = None
    status: Literal["normal", "violation", "uncertain"] = "uncertain"
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    description: str = ""


class ClaimRecord(StrictModel):
    claim_id: str
    claim: str
    predicted_fault_type: str | None = None
    predicted_root_module: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class DiagnosisRecord(StrictModel):
    scenario_id: str
    predicted_fault_type: str | None = None
    predicted_root_module: str | None = None
    predicted_fault_start_time: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
