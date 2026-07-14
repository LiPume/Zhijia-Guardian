"""Small synthetic evaluation harness for routing and conclusion-boundary checks.

This is deliberately an evaluator: it may read synthetic manifests after the
workflow ends, but the workflow itself only receives the oracle-free case.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from zhijia_guardian.adapters.synthetic_adapter import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow.graph import run_diagnostic_workflow


EXPECTED_LINKS = {
  "perception_dropout": {"modelV2 -> longitudinalPlan"},
  "planner_gap": {"longitudinalPlan -> carControl"},
  "sendcan_gap": {"carControl -> sendcan"},
  "perception_and_sendcan_gap": {"modelV2 -> longitudinalPlan", "carControl -> sendcan"},
}


@dataclass
class EvaluationRow:
  fault_kind: str
  routing_policy: str
  predicted_link: str | None
  expected_links: list[str]
  top1_correct: bool
  classification: str | None
  evidence_complete: bool
  tool_calls: int
  trace_agents: list[str]


def evaluate_synthetic_fault_matrix(*, routing_policies: tuple[str, ...] = ("adaptive", "fixed")) -> list[EvaluationRow]:
  rows: list[EvaluationRow] = []
  for fault_kind, expected_links in EXPECTED_LINKS.items():
    clean = generate_clean_case(case_id=f"matrix-{fault_kind}-clean")
    perturbed, _ = inject_perturbation(clean, kind=fault_kind)
    for routing_policy in routing_policies:
      diagnosis, state = run_diagnostic_workflow(perturbed, intervention_reference=clean, routing_policy=routing_policy)
      finding = diagnosis.findings[0] if diagnosis.findings else None
      rows.append(EvaluationRow(
        fault_kind=fault_kind, routing_policy=routing_policy, predicted_link=finding.suspected_link if finding else None,
        expected_links=sorted(expected_links), top1_correct=bool(finding and finding.suspected_link in expected_links),
        classification=finding.classification if finding else None,
        evidence_complete=bool(finding and finding.evidence_ids), tool_calls=state.tool_calls,
        trace_agents=[item.agent for item in state.trace],
      ))
  return rows


def summarize_matrix(rows: list[EvaluationRow]) -> dict:
  summary = {}
  for policy in sorted({item.routing_policy for item in rows}):
    subset = [item for item in rows if item.routing_policy == policy]
    summary[policy] = {
      "cases": len(subset),
      "top1_accuracy": sum(item.top1_correct for item in subset) / len(subset) if subset else 0.0,
      "evidence_complete_rate": sum(item.evidence_complete for item in subset) / len(subset) if subset else 0.0,
      "mean_tool_calls": sum(item.tool_calls for item in subset) / len(subset) if subset else 0.0,
    }
  return {"rows": [asdict(item) for item in rows], "summary": summary}
