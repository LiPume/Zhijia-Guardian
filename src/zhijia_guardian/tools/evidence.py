from __future__ import annotations

from itertools import count
from typing import Iterable

from zhijia_guardian.schema.models import DiagnosticCase, Evidence, Finding, TimeRange, ToolResult

_ids = count(1)


def create_evidence(kind: str, summary: str, source_tool: str, *, topic: str | None = None, time_window: TimeRange | None = None, metrics: dict | None = None, limitations: list[str] | None = None) -> Evidence:
  return Evidence(evidence_id=f"ev-{next(_ids):04d}", kind=kind, summary=summary, source_tool=source_tool, topic=topic, time_window=time_window, metrics=metrics or {}, limitations=limitations or [])


def result(tool_name: str, status: str, *, metrics: dict | None = None, evidence: list[Evidence] | None = None, limitations: list[str] | None = None, time_window: TimeRange | None = None) -> ToolResult:
  return ToolResult(tool_name=tool_name, status=status, metrics=metrics or {}, evidence=evidence or [], limitations=limitations or [], time_window=time_window)


def validate_evidence_references(findings: Iterable[Finding], evidence: Iterable[Evidence]) -> list[str]:
  known = {item.evidence_id for item in evidence}
  return [f"{finding.finding_id} references unknown evidence {evidence_id}" for finding in findings for evidence_id in finding.evidence_ids if evidence_id not in known]


def rank_suspected_links(case: DiagnosticCase) -> list[Finding]:
  gaps = [e for e in case.evidence if e.kind in {"message_gap", "can_gap", "control_inconsistency"}]
  # Prefer the earliest direct message-gap evidence. A single transport outage can
  # generate several derivative CAN/control symptoms; do not report each as a new cause.
  direct = [e for e in gaps if e.kind == "message_gap"]
  selected = direct or gaps
  unique: dict[str, Evidence] = {}
  for evidence in selected:
    link = "carControl -> sendcan" if evidence.topic == "sendcan" else f"producer -> {evidence.topic or 'unknown'}"
    unique.setdefault(link, evidence)
  findings: list[Finding] = []
  for i, (link, evidence) in enumerate(unique.items(), 1):
    topic = evidence.topic or "unknown"
    findings.append(Finding(finding_id=f"finding-{i:03d}", classification="suspected_link", suspected_link=link,
                            statement=f"Observed anomaly on {topic}; this supports a suspected message/control-chain link, not a root cause.", confidence=0.7,
                            evidence_ids=[evidence.evidence_id], limitations=list(evidence.limitations)))
  if not findings and case.evidence:
    findings.append(Finding(finding_id="finding-001", classification="cannot_determine_root_cause", statement="No evidence supports a specific abnormal link in the observable topics.",
                            confidence=0.2, evidence_ids=[case.evidence[0].evidence_id], limitations=["absence of evidence is not evidence of absence"]))
  return findings
