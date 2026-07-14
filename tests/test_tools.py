from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.tools import detect_message_gaps, summarize_can_addresses


def test_detect_sendcan_gap_and_can_addresses():
  case, _ = inject_perturbation(generate_clean_case())
  gap = detect_message_gaps(case, "sendcan")
  assert gap.status == "ok" and gap.evidence
  assert summarize_can_addresses(case, "can").status == "ok"
