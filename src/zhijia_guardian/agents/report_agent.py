from __future__ import annotations

from zhijia_guardian.schemas.diagnosis import DiagnosisRecord


def render_markdown_report(diagnosis: DiagnosisRecord) -> str:
    lines = [
        f"# Diagnosis {diagnosis.scenario_id}",
        "",
        "## Summary",
        "",
        f"- method: `{diagnosis.method}`",
        f"- predicted_fault_type: `{diagnosis.predicted_fault_type}`",
        f"- predicted_root_module: `{diagnosis.predicted_root_module}`",
        f"- predicted_fault_start_time: `{diagnosis.predicted_fault_start_time}`",
        f"- confidence: `{diagnosis.confidence:.2f}`",
        "",
        "## Candidate Root Causes",
        "",
    ]
    for index, candidate in enumerate(diagnosis.candidate_root_causes, start=1):
        evidence_ids = ", ".join(candidate.evidence_ids) or "none"
        lines.append(
            f"{index}. `{candidate.fault_type}` / `{candidate.root_module}` "
            f"score={candidate.score:.2f} confidence={candidate.confidence:.2f} evidence={evidence_ids}"
        )
        if candidate.rationale:
            lines.append(f"   - {candidate.rationale}")

    lines.extend(["", "## Agent Trace", ""])
    for step in diagnosis.agent_trace:
        evidence_ids = ", ".join(step.evidence_ids) or "none"
        lines.append(f"- `{step.agent_name}` {step.status}: {step.summary} evidence={evidence_ids}")

    lines.extend(["", "## Claims", ""])
    for claim in diagnosis.claims:
        evidence_ids = ", ".join(claim.evidence_ids) or "none"
        lines.append(f"- `{claim.claim_id}` {claim.claim} evidence={evidence_ids}")

    lines.extend(["", "## Evidence", ""])
    for evidence in diagnosis.evidence:
        lines.append(
            f"- `{evidence.evidence_id}` `{evidence.metric_name}` {evidence.status}: {evidence.description}"
        )
    return "\n".join(lines) + "\n"
