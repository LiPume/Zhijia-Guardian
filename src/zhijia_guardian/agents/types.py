from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ModuleDiagnosis(StrictModel):
    module_name: str
    status: Literal["completed", "skipped", "uncertain"] = "completed"
    predicted_fault_type: str | None = None
    predicted_root_module: str | None = None
    score: float = 0.0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    start_time: float | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    summary: str = ""

    @property
    def evidence_ids(self) -> list[str]:
        return [item.evidence_id for item in self.evidence]
