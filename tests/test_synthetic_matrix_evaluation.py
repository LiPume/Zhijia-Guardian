from zhijia_guardian.evaluation import evaluate_synthetic_fault_matrix, summarize_matrix


def test_adaptive_routing_is_correct_on_small_fault_matrix_and_uses_no_more_tools_than_fixed():
  rows = evaluate_synthetic_fault_matrix()
  summary = summarize_matrix(rows)["summary"]
  assert summary["adaptive"]["top1_accuracy"] == 1.0
  assert summary["adaptive"]["evidence_complete_rate"] == 1.0
  assert summary["adaptive"]["mean_tool_calls"] <= summary["fixed"]["mean_tool_calls"]
