import pytest
from pydantic import ValidationError

from zhijia_guardian.agents.report_agent import (
    REPORT_SCHEMA_VERSION,
    REPORT_SECTION_ORDER,
    render_markdown_report,
)
from zhijia_guardian.experiments.eval_metrics import EvalRow
from zhijia_guardian.experiments.failure_sample_builder import build_failure_sample
from zhijia_guardian.schemas.diagnosis import (
    CandidateRootCause,
    ClaimRecord,
    DiagnosisRecord,
    EvidenceRecord,
)
from zhijia_guardian.schemas.failure_sample import FailureSampleRecord
from zhijia_guardian.schemas.scenario import (
    EgoState,
    FrameRecord,
    MetaInfo,
    OracleRecord,
    ScenarioRecord,
    SourceInfo,
)


def _record() -> ScenarioRecord:
    return ScenarioRecord(
        scenario_id="contract_000001",
        source=SourceInfo(dataset="test", version="v1"),
        meta=MetaInfo(frequency_hz=10.0, duration=0.0),
        frames=[FrameRecord(timestamp=0.0, ego=EgoState(x=0.0, y=0.0))],
        oracle=OracleRecord(
            fault_type="control_delay",
            root_module="control",
            fault_start_time=1.0,
        ),
    )


def _diagnosis() -> DiagnosisRecord:
    evidence = EvidenceRecord(
        evidence_id="E_CTRL_001",
        metric_name="brake_delay",
        value=1.0,
        threshold=0.6,
        time=1.0,
        status="violation",
        supports=["control_delay"],
    )
    return DiagnosisRecord(
        scenario_id="contract_000001",
        predicted_fault_type="control_delay",
        predicted_root_module="control",
        predicted_fault_start_time=1.0,
        confidence=0.8,
        method="multi_agent_tools",
        candidate_root_causes=[
            CandidateRootCause(
                fault_type="control_delay",
                root_module="control",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        evidence=[evidence],
        claims=[
            ClaimRecord(
                claim_id="C_001",
                claim="Brake response is delayed.",
                predicted_fault_type="control_delay",
                predicted_root_module="control",
                evidence_ids=[evidence.evidence_id],
            )
        ],
    )


def _eval_row() -> EvalRow:
    return EvalRow(
        scenario_id="contract_000001",
        true_fault_type="control_delay",
        pred_fault_type="control_delay",
        true_root_module="control",
        pred_root_module="control",
        true_fault_start_time=1.0,
        pred_fault_start_time=1.0,
        fault_correct=True,
        root_correct=True,
        fault_time_eligible=True,
        fault_time_predicted=True,
        fault_time_covered=True,
        time_abs_error=0.0,
        time_abs_error_at_correct_fault=0.0,
        evidence_coverage=1.0,
        evidence_correctness=1.0,
        hallucination_rate=0.0,
    )


def test_failure_sample_is_versioned_strict_and_round_trippable():
    sample = build_failure_sample(_record(), _diagnosis(), _eval_row(), "multi_agent_tools")

    assert sample is not None
    assert sample.schema_version == "failure_sample_v1"
    assert sample.oracle_visibility == "evaluation_only"
    assert sample.regression_test_config.diagnosis_input == "observed_view_only"
    assert FailureSampleRecord.model_validate_json(sample.model_dump_json()) == sample

    invalid = sample.model_dump(mode="json")
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        FailureSampleRecord.model_validate(invalid)


def test_diagnosis_report_has_version_and_stable_section_order():
    report = render_markdown_report(
        _diagnosis(),
        {"bev": "../figures/bev.svg", "timeline": "../figures/timeline.svg"},
    )

    assert report.startswith("# Diagnosis Report contract_000001")
    assert f"report_schema_version: `{REPORT_SCHEMA_VERSION}`" in report
    positions = [report.index(f"## {section}") for section in REPORT_SECTION_ORDER]
    assert positions == sorted(positions)
    assert "`E_CTRL_001`" in report
    assert "## Recommended Actions" in report
    assert "oracle" not in report.lower()
