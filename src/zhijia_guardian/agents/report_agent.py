from __future__ import annotations

from zhijia_guardian.schemas.diagnosis import DiagnosisRecord


REPORT_SCHEMA_VERSION = "diagnosis_report_v1"
REPORT_SECTION_ORDER = (
    "Metadata",
    "Diagnosis Summary",
    "Figures",
    "Candidate Root Causes",
    "Evidence Chain",
    "Claims",
    "Agent Execution Trace",
    "Uncertainty And Limitations",
    "Recommended Actions",
)


def render_markdown_report(
    diagnosis: DiagnosisRecord,
    figure_paths: dict[str, str] | None = None,
) -> str:
    lines = [
        f"# Diagnosis Report {diagnosis.scenario_id}",
        "",
        "## Metadata",
        "",
        f"- report_schema_version: `{REPORT_SCHEMA_VERSION}`",
        f"- diagnosis_schema_version: `{diagnosis.schema_version}`",
        f"- scenario_id: `{diagnosis.scenario_id}`",
        f"- method: `{diagnosis.method}`",
        "",
        "## Diagnosis Summary",
        "",
        f"- predicted_fault_type: `{diagnosis.predicted_fault_type}`",
        f"- predicted_root_module: `{diagnosis.predicted_root_module}`",
        f"- predicted_fault_start_time: `{diagnosis.predicted_fault_start_time}`",
        f"- confidence: `{diagnosis.confidence:.2f}`",
        "",
        "## Figures",
        "",
    ]
    if figure_paths and figure_paths.get("bev"):
        lines.extend([f"![BEV]({figure_paths['bev']})", ""])
    if figure_paths and figure_paths.get("timeline"):
        lines.extend([f"![Timeline]({figure_paths['timeline']})", ""])
    if not figure_paths:
        lines.extend(["No figures were attached to this report.", ""])

    lines.extend(["## Candidate Root Causes", ""])
    if diagnosis.candidate_root_causes:
        for index, candidate in enumerate(diagnosis.candidate_root_causes, start=1):
            evidence_ids = ", ".join(candidate.evidence_ids) or "none"
            lines.append(
                f"{index}. `{candidate.fault_type}` / `{candidate.root_module}` "
                f"score={candidate.score:.2f} confidence={candidate.confidence:.2f} "
                f"evidence={evidence_ids}"
            )
            if candidate.rationale:
                lines.append(f"   - rationale: {candidate.rationale}")
    else:
        lines.append("No candidate root cause was produced.")

    lines.extend(["", "## Evidence Chain", ""])
    if diagnosis.evidence:
        lines.extend(
            [
                "| Evidence ID | Metric | Status | Time | Value | Threshold | Supports | Contradicts |",
                "| --- | --- | --- | ---: | --- | --- | --- | --- |",
            ]
        )
        for evidence in diagnosis.evidence:
            lines.append(
                f"| `{evidence.evidence_id}` | `{evidence.metric_name}` | `{evidence.status}` | "
                f"{_display(evidence.time)} | {_display(evidence.value)} | "
                f"{_display(evidence.threshold)} | {_labels(evidence.supports)} | "
                f"{_labels(evidence.contradicts)} |"
            )
    else:
        lines.append("No diagnosable evidence is available.")

    lines.extend(["", "## Claims", ""])
    if diagnosis.claims:
        for claim in diagnosis.claims:
            evidence_ids = ", ".join(claim.evidence_ids) or "none"
            lines.append(
                f"- `{claim.claim_id}` {claim.claim} "
                f"fault=`{claim.predicted_fault_type}` root=`{claim.predicted_root_module}` "
                f"evidence={evidence_ids}"
            )
    else:
        lines.append("No claims were produced.")

    lines.extend(["", "## Agent Execution Trace", ""])
    if diagnosis.agent_trace:
        for index, step in enumerate(diagnosis.agent_trace, start=1):
            evidence_ids = ", ".join(step.evidence_ids) or "none"
            lines.append(
                f"{index}. `{step.agent_name}` status=`{step.status}` "
                f"evidence={evidence_ids}: {step.summary}"
            )
    else:
        lines.append("No agent trace is available for this method.")

    lines.extend(["", "## Uncertainty And Limitations", ""])
    lines.extend(_limitations(diagnosis))

    lines.extend(["", "## Recommended Actions", ""])
    lines.extend(_recommended_actions(diagnosis.predicted_root_module))
    return "\n".join(lines) + "\n"


def _limitations(diagnosis: DiagnosisRecord) -> list[str]:
    skipped = [step.agent_name for step in diagnosis.agent_trace if step.status == "skipped"]
    limitations = [
        "- This is an offline diagnostic hypothesis, not a legal or safety certification conclusion.",
        "- Conclusions are limited to the observed fields and deterministic evidence listed above.",
    ]
    if skipped:
        limitations.append(f"- Skipped agents due to unavailable inputs: `{', '.join(skipped)}`.")
    if diagnosis.predicted_fault_type == "uncertain" or diagnosis.confidence < 0.5:
        limitations.append("- Confidence is limited; collect missing module logs before engineering sign-off.")
    return limitations


def _recommended_actions(root_module: str | None) -> list[str]:
    actions = {
        "perception": [
            "- Review the sensor clip, detection association, confidence trend, and visibility around the fault window.",
            "- Add the scenario to perception regression data with weather and occlusion tags.",
        ],
        "planning": [
            "- Replay candidate trajectories and planner cost/debug outputs against the cited actor states.",
            "- Add a collision-margin regression assertion for the same route and obstacle interaction.",
        ],
        "control": [
            "- Compare control commands with actuator feedback and measure brake/throttle response latency.",
            "- Add a command-tracking regression test using the cited risk start time.",
        ],
        "none": [
            "- Preserve this scenario as a normal or boundary regression sample.",
            "- Monitor threshold drift before changing production configuration.",
        ],
    }
    return actions.get(
        root_module or "unknown",
        [
            "- Collect perception, planning, control, and actor reconstruction logs for the same time window.",
            "- Keep the case in manual review until a module-level evidence chain is available.",
        ],
    )


def _display(value: object) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "\\|")


def _labels(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) or "-"
