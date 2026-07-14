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
  lines += ["", "## Hypothesis board", ""]
  for item in diagnosis.hypotheses:
    lines.append(f"- `{item.hypothesis_id}` ({item.status}, {item.confidence:.2f}): {item.statement} Next action: `{item.next_action}`.")
  if diagnosis.decision_board:
    lines += ["", "## Decision board", ""]
    for item in diagnosis.decision_board.action_candidates:
      selected = " ← selected" if item.action_id == diagnosis.decision_board.chosen_action_id else ""
      lines.append(f"- `{item.action_id}`: {item.action}; diagnostic-priority/cost `{item.diagnostic_priority_score:.2f}/{item.estimated_cost:.2f}`; feasible={item.feasible}{selected}")
  lines += ["", "## Intervention and validation", ""]
  for item in diagnosis.interventions:
    lines.append(f"- `{item.intervention_id}`: {item.status}; {item.action}; {item.rationale}")
  for item in diagnosis.validations:
    lines.append(f"- `{item.validation_id}`: **{item.status}** — {item.observed_result}")
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
  write_json({"case_id": case.case_id, "hypotheses": [item.model_dump() for item in diagnosis.hypotheses]}, root / "hypotheses.json")
  write_json({"case_id": case.case_id, "interventions": [item.model_dump() for item in diagnosis.interventions], "validations": [item.model_dump() for item in diagnosis.validations]}, root / "interventions.json")
  write_json(diagnosis.decision_board or {"case_id": case.case_id, "action_candidates": []}, root / "decision_board.json")
  report_path = root / "report.md"
  report_path.write_text(render_diagnosis_report(diagnosis, case.evidence, trace), encoding="utf-8")
  package = root / "failure_sample_package"
  package.mkdir(exist_ok=True)
  manifest = {"case_id": case.case_id, "source": case.source.model_dump(), "contains_raw_log": False, "files": ["diagnosis.json", "evidence.jsonl", "agent_trace.json", "hypotheses.json", "interventions.json", "decision_board.json", "report.md"], "limitations": diagnosis.limitations}
  (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
  return {"root": root, "diagnosis": diagnosis_path, "evidence": evidence_path, "trace": trace_path, "hypotheses": root / "hypotheses.json", "interventions": root / "interventions.json", "decision_board": root / "decision_board.json", "report": report_path, "package": package}
