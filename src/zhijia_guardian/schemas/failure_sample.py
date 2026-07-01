from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.scenario import StrictModel


class FailureSampleSource(StrictModel):
    dataset: str
    version: str
    raw_log_id: str | None = None
    raw_tokens: dict[str, Any] = Field(default_factory=dict)


class RecommendedDataRecord(StrictModel):
    name: str
    reason: str
    priority: Literal["high", "medium", "low"]


class ScenarioSelector(StrictModel):
    scenario_id: str
    dataset: str
    version: str
    raw_log_id: str | None = None


class ExpectedDiagnosis(StrictModel):
    fault_type: str
    root_module: str
    fault_start_time: float | None = None


class RegressionTolerance(StrictModel):
    fault_start_time_abs_error_s: float = Field(default=0.5, ge=0.0)


class RegressionTestConfig(StrictModel):
    scenario_selector: ScenarioSelector
    diagnosis_input: Literal["observed_view_only"] = "observed_view_only"
    method_under_test: str
    threshold_config: str
    llm_config: str
    expected: ExpectedDiagnosis
    tolerances: RegressionTolerance = Field(default_factory=RegressionTolerance)


class FailureSampleRecord(StrictModel):
    schema_version: Literal["failure_sample_v1"] = "failure_sample_v1"
    package_kind: Literal["diagnosis_failure_sample"] = "diagnosis_failure_sample"
    oracle_visibility: Literal["evaluation_only"] = "evaluation_only"
    scenario_id: str
    source: FailureSampleSource
    diagnosis_method: str
    predicted_fault_type: str
    predicted_root_module: str
    predicted_fault_start_time: float | None = None
    true_fault_type: str
    true_root_module: str
    true_fault_start_time: float | None = None
    is_correct: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    wrong_reasoning: str
    correct_reasoning: str
    tags: list[str] = Field(default_factory=list)
    recommended_data: list[RecommendedDataRecord] = Field(default_factory=list)
    regression_test_config: RegressionTestConfig
    scenario_record_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> "FailureSampleRecord":
        selector = self.regression_test_config.scenario_selector
        if selector.scenario_id != self.scenario_id:
            raise ValueError("regression scenario_id must match failure sample scenario_id")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("failure sample evidence_id values must be unique")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("failure sample tags must be unique")
        return self
