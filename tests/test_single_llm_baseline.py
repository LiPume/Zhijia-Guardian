import json
import subprocess
import sys
from pathlib import Path

import pytest

from zhijia_guardian.adapters import ManualAdapter
from zhijia_guardian.baselines.single_llm import (
    LLMCandidate,
    LLMClaim,
    LLMGeneration,
    SingleLLMOutput,
    build_single_llm_input,
    create_single_llm_client,
    diagnose_single_llm,
    load_llm_config,
)
from zhijia_guardian.experiments.eval_metrics import evidence_quality
from zhijia_guardian.experiments.run_eval import run_single_llm_eval
from zhijia_guardian.tools.run_metrics import run_all_metrics


REPO_ROOT = Path(__file__).resolve().parents[1]


class SpySingleLLMClient:
    def __init__(self, evidence_id: str | None = None) -> None:
        self.evidence_id = evidence_id
        self.payloads: list[dict] = []

    def generate_diagnosis(self, system_prompt: str, user_payload: dict) -> LLMGeneration:
        self.payloads.append(user_payload)
        evidence_id = self.evidence_id or next(
            item["evidence_id"]
            for item in user_payload["metrics_summary"]["evidence"]
            if item["metric_name"] == "missed_key_actors"
        )
        output = SingleLLMOutput(
            predicted_fault_type="perception_miss",
            predicted_root_module="perception",
            predicted_fault_start_time=2.0,
            confidence=0.9,
            candidate_root_causes=[
                LLMCandidate(
                    fault_type="perception_miss",
                    root_module="perception",
                    confidence=0.9,
                    evidence_ids=[evidence_id],
                    rationale="Key actors are absent from detections.",
                )
            ],
            claims=[
                LLMClaim(
                    claim="A key actor is missed by perception.",
                    predicted_fault_type="perception_miss",
                    predicted_root_module="perception",
                    evidence_ids=[evidence_id],
                )
            ],
        )
        return LLMGeneration(output=output, metadata={"provider": "test", "input_tokens": 10})


@pytest.fixture
def demo_dataset(tmp_path):
    dataset_dir = tmp_path / "canonical_demo"
    subprocess.check_call(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_canonical_demo.py"),
            "--output-dir",
            str(dataset_dir),
        ],
        cwd=REPO_ROOT,
    )
    return dataset_dir


def test_single_llm_input_is_sanitized_and_diagnosis_uses_common_schema(demo_dataset):
    record = ManualAdapter(demo_dataset).load_scenario("manual_v0_1_000001")
    record.source.generation = {"private_marker": "oracle_secret_perception_miss"}
    record.oracle.notes = "oracle_secret_perception_miss"
    metrics = run_all_metrics(record)

    payload = build_single_llm_input(record, metrics)
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in [
        "oracle",
        "generation",
        "supports",
        "contradicts",
        "scenario_id",
        "raw_log_id",
        "oracle_secret_perception_miss",
    ]:
        assert forbidden not in serialized

    client = SpySingleLLMClient()
    diagnosis = diagnose_single_llm(record, metrics, client)
    assert diagnosis.method == "single_llm"
    assert diagnosis.predicted_fault_type == "perception_miss"
    assert diagnosis.agent_trace[0].output["input_tokens"] == 10
    assert diagnosis.evidence == metrics.evidence
    assert evidence_quality(diagnosis) == (1.0, 1.0, 0.0)


def test_single_llm_unknown_evidence_is_counted_as_hallucination(demo_dataset):
    record = ManualAdapter(demo_dataset).load_scenario("manual_v0_1_000001")
    metrics = run_all_metrics(record)
    diagnosis = diagnose_single_llm(record, metrics, SpySingleLLMClient("E_INVENTED_999"))
    coverage, correctness, hallucination = evidence_quality(diagnosis)
    assert coverage == 1.0
    assert correctness == 0.0
    assert hallucination == 1.0


def test_single_llm_preserves_semantic_root_mismatch_for_evaluation():
    claim = LLMClaim(
        claim="The model produced an inconsistent semantic pair.",
        predicted_fault_type="normal",
        predicted_root_module="perception",
        evidence_ids=[],
    )
    assert claim.predicted_root_module == "perception"


def test_single_llm_eval_supports_injected_client_and_limit(demo_dataset, tmp_path):
    client = SpySingleLLMClient()
    run_dir = run_single_llm_eval(
        dataset=demo_dataset / "perception_like_nuscenes",
        run_id="pytest_single_llm_demo",
        output_root=tmp_path / "runs",
        llm_client=client,
        limit=1,
    )
    assert len(client.payloads) == 1

    run_single_llm_eval(
        dataset=demo_dataset / "perception_like_nuscenes",
        run_id="pytest_single_llm_demo",
        output_root=tmp_path / "runs",
        llm_client=client,
        limit=1,
        resume=True,
    )
    assert len(client.payloads) == 1
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    run_meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    diagnosis = json.loads(
        (run_dir / "diagnoses" / "manual_v0_1_000001.json").read_text(encoding="utf-8")
    )
    assert summary["num_scenarios"] == 1
    assert summary["hallucination_rate"] == 0.0
    assert run_meta["method"] == "single_llm"
    assert run_meta["scenario_limit"] == 1
    assert run_meta["resume"] is True
    assert run_meta["llm"]["model"] == "gpt-4o-mini"
    assert diagnosis["method"] == "single_llm"


def test_single_llm_default_config_requires_explicit_enable():
    config = load_llm_config(REPO_ROOT / "configs" / "llm.yaml")
    assert config.enabled is False
    with pytest.raises(RuntimeError, match="disabled"):
        create_single_llm_client(config)


def test_deepseek_config_uses_chat_json_object_surface():
    config = load_llm_config(REPO_ROOT / "configs" / "llm_deepseek.yaml")
    assert config.provider == "deepseek"
    assert config.model == "deepseek-v4-pro"
    assert config.endpoint == "chat_completions"
    assert config.structured_output == "json_object"
    assert config.api_key_env == "DEEPSEEK_API_KEY"
