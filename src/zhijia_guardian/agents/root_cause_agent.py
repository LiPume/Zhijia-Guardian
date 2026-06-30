from __future__ import annotations

from zhijia_guardian.agents.scoring import LABEL_PRIORITY, ROOT_MODULE
from zhijia_guardian.agents.types import ModuleDiagnosis
from zhijia_guardian.schemas.diagnosis import AgentStepRecord, CandidateRootCause, ClaimRecord, DiagnosisRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


def run_root_cause_agent(
    scenario: ScenarioRecord,
    metrics: MetricsRecord,
    module_diagnoses: list[ModuleDiagnosis],
    existing_trace: list[AgentStepRecord],
) -> DiagnosisRecord:
    candidates = _build_candidates(module_diagnoses)
    if candidates:
        predicted = candidates[0].fault_type
        root_module = candidates[0].root_module
        start_time = _earliest_time_by_ids(metrics, candidates[0].evidence_ids)
        confidence = candidates[0].confidence
        final_evidence_ids = candidates[0].evidence_ids
    else:
        normal_evidence = [item for item in metrics.evidence if "normal" in item.supports]
        predicted = "normal" if normal_evidence else "uncertain"
        root_module = "none" if normal_evidence else "unknown"
        start_time = None
        confidence = 0.65 if normal_evidence else 0.0
        final_evidence_ids = [item.evidence_id for item in normal_evidence[:6]]
        candidates = [
            CandidateRootCause(
                fault_type=predicted,
                root_module=root_module,
                score=sum(1.0 for _ in normal_evidence),
                confidence=confidence,
                evidence_ids=final_evidence_ids,
                rationale=(
                    "Available module evidence supports normal operation."
                    if normal_evidence
                    else "No diagnosable module evidence is available; normal operation cannot be established."
                ),
            )
        ]

    claims = _module_claims(module_diagnoses)
    claims.append(
        ClaimRecord(
            claim_id=f"C_{len(claims) + 1:03d}",
            claim=f"Multi-Agent + Tools predicts {predicted}.",
            predicted_fault_type=predicted,
            predicted_root_module=root_module,
            evidence_ids=final_evidence_ids,
        )
    )
    trace = list(existing_trace)
    trace.extend(_module_trace(module_diagnoses))
    trace.append(
        AgentStepRecord(
            agent_name="root_cause_agent",
            status="completed",
            summary=f"Ranked {len(candidates)} candidate root causes; top-1 is {predicted}.",
            evidence_ids=final_evidence_ids,
            output={"top_fault_type": predicted, "top_root_module": root_module},
        )
    )
    return DiagnosisRecord(
        scenario_id=scenario.scenario_id,
        predicted_fault_type=predicted,
        predicted_root_module=root_module,
        predicted_fault_start_time=start_time,
        confidence=confidence,
        method="multi_agent_tools",
        candidate_root_causes=candidates,
        agent_trace=trace,
        evidence=metrics.evidence,
        claims=claims,
    )


def _build_candidates(module_diagnoses: list[ModuleDiagnosis]) -> list[CandidateRootCause]:
    candidates = []
    for module in module_diagnoses:
        label = module.predicted_fault_type
        if module.status != "completed" or label in {None, "normal"}:
            continue
        adjusted_score = _adjusted_score(module, module_diagnoses)
        candidates.append(
            CandidateRootCause(
                fault_type=label,
                root_module=module.predicted_root_module or ROOT_MODULE.get(label, module.module_name),
                score=adjusted_score,
                confidence=min(1.0, adjusted_score / 5.0),
                evidence_ids=module.evidence_ids,
                rationale=f"{module.summary} causal_score={adjusted_score:.2f} raw_score={module.score:.2f}.",
            )
        )
    candidates.sort(key=lambda item: (-item.score, _priority_rank(item.fault_type)))
    return candidates


def _adjusted_score(module: ModuleDiagnosis, module_diagnoses: list[ModuleDiagnosis]) -> float:
    score = module.score
    downstream_candidates = [
        other
        for other in module_diagnoses
        if other.status == "completed"
        and other.predicted_fault_type not in {None, "normal"}
        and _module_rank(module.module_name) < _module_rank(other.module_name)
    ]
    earlier_than_downstream = any(
        module.start_time is not None
        and other.start_time is not None
        and module.start_time + 0.25 < other.start_time
        for other in downstream_candidates
    )
    if earlier_than_downstream:
        score += {"perception": 1.25, "planning": 1.10}.get(module.module_name, 0.0)
        score += 0.75
    return score


def _module_claims(module_diagnoses: list[ModuleDiagnosis]) -> list[ClaimRecord]:
    claims = []
    for module in module_diagnoses:
        if module.status != "completed" or not module.predicted_fault_type or not module.evidence_ids:
            continue
        claims.append(
            ClaimRecord(
                claim_id=f"C_{len(claims) + 1:03d}",
                claim=module.summary,
                predicted_fault_type=module.predicted_fault_type,
                predicted_root_module=module.predicted_root_module,
                evidence_ids=module.evidence_ids,
            )
        )
    return claims


def _module_trace(module_diagnoses: list[ModuleDiagnosis]) -> list[AgentStepRecord]:
    trace = []
    for module in module_diagnoses:
        trace.append(
            AgentStepRecord(
                agent_name=f"{module.module_name}_agent",
                status=module.status,
                summary=module.summary,
                evidence_ids=module.evidence_ids,
                output={
                    "predicted_fault_type": module.predicted_fault_type,
                    "predicted_root_module": module.predicted_root_module,
                    "score": module.score,
                    "confidence": module.confidence,
                },
            )
        )
    return trace


def _earliest_time_by_ids(metrics: MetricsRecord, evidence_ids: list[str]) -> float | None:
    ids = set(evidence_ids)
    times = [item.time for item in metrics.evidence if item.evidence_id in ids and item.time is not None]
    return min(times) if times else None


def _priority_rank(label: str) -> int:
    return LABEL_PRIORITY.index(label) if label in LABEL_PRIORITY else 999


def _module_rank(module_name: str) -> int:
    return {"perception": 0, "planning": 1, "control": 2}.get(module_name, 99)
