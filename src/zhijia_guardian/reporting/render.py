from __future__ import annotations

import json
from pathlib import Path

from zhijia_guardian.schema.models import AgentTraceEntry, Diagnosis, DiagnosticCase, Evidence, write_json


def render_diagnosis_report(diagnosis: Diagnosis, evidence: list[Evidence], trace: list[AgentTraceEntry]) -> str:
  lines = [f"# Zhijia-Guardian Diagnosis: {diagnosis.case_id}", "", "## Scope", "",
           f"- Source: `{diagnosis.source.dataset}`; synthetic: `{diagnosis.source.is_synthetic}`.",
           "- This is an offline suspected-link analysis of observable openpilot-like messages; it does not determine a real-world root cause.", "", "## Audited findings", ""]
  for finding in diagnosis.findings:
    lines += [f"- **{finding.classification}** — {finding.statement}", f"  - Link: `{finding.suspected_link or 'not determined'}`; confidence: {finding.confidence:.2f}; evidence: {', '.join(finding.evidence_ids)}."]
  lines += ["", "## Evidence", ""]
  for item in evidence:
    lines.append(f"- `{item.evidence_id}` ({item.source_tool}): {item.summary}")
  lines += ["", "## Agent trace", ""]
  for item in trace:
    lines.append(f"- {item.step}. `{item.agent}` — tools: {', '.join(item.tools_called) or 'none'}; {item.output_summary}")
  lines += ["", "## Limitations", ""] + [f"- {x}" for x in diagnosis.limitations] + ["", f"Stop reason: `{diagnosis.stop_reason}`."]
  return "\n".join(lines) + "\n"


def write_artifacts(output_root: str | Path, case: DiagnosticCase, diagnosis: Diagnosis, trace: list[AgentTraceEntry]) -> dict[str, Path]:
  root = Path(output_root) / case.case_id
  root.mkdir(parents=True, exist_ok=True)
  diagnosis_path, evidence_path, trace_path = root / "diagnosis.json", root / "evidence.jsonl", root / "agent_trace.json"
  diagnosis.agent_trace_path = str(trace_path)
  write_json(diagnosis, diagnosis_path)
  evidence_path.write_text("".join(item.model_dump_json() + "\n" for item in case.evidence), encoding="utf-8")
  write_json({"case_id": case.case_id, "trace": [entry.model_dump() for entry in trace]}, trace_path)
  report_path = root / "report.md"
  report_path.write_text(render_diagnosis_report(diagnosis, case.evidence, trace), encoding="utf-8")
  package = root / "failure_sample_package"
  package.mkdir(exist_ok=True)
  manifest = {"case_id": case.case_id, "source": case.source.model_dump(), "contains_raw_log": False, "files": ["diagnosis.json", "evidence.jsonl", "agent_trace.json", "report.md"], "limitations": diagnosis.limitations}
  (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
  return {"root": root, "diagnosis": diagnosis_path, "evidence": evidence_path, "trace": trace_path, "report": report_path, "package": package}
