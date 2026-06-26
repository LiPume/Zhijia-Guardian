from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MetricSeries(StrictModel):
    name: str
    timestamps: list[float] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)


class MetricsRecord(StrictModel):
    scenario_id: str
    series: list[MetricSeries] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
