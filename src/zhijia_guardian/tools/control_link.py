from __future__ import annotations

from zhijia_guardian.schema.models import DiagnosticCase, ToolResult
from .can_analysis import extract_can_frames
from .evidence import create_evidence, result
from .message_flow import detect_message_gaps, extract_topic_messages


def find_first_divergence(case: DiagnosticCase, upstream: str, downstream: str, max_delay_s: float = 0.25) -> ToolResult:
  left, right = extract_topic_messages(case, upstream), extract_topic_messages(case, downstream)
  if not left or not right:
    return result("find_first_divergence", "insufficient_observability", limitations=[f"need {upstream} and {downstream}"])
  for message in left:
    following = [other for other in right if other.mono_time >= message.mono_time]
    if not following or (following[0].mono_time - message.mono_time) / 1e9 > max_delay_s:
      evidence = create_evidence("control_inconsistency", f"No {downstream} message within {max_delay_s:.3f}s after {upstream}.", "find_first_divergence", topic=downstream, metrics={"upstream": upstream, "downstream": downstream})
      return result("find_first_divergence", "ok", metrics={"divergence_found": True, "at_ns": message.mono_time}, evidence=[evidence])
  return result("find_first_divergence", "ok", metrics={"divergence_found": False})


def check_control_command_response(case: DiagnosticCase) -> ToolResult:
  controls, states = extract_topic_messages(case, "carControl"), extract_topic_messages(case, "carState")
  if not controls or not states:
    return result("check_control_command_response", "insufficient_observability", limitations=["carControl or carState unavailable"])
  delays = []
  for command in controls:
    later = next((state for state in states if state.mono_time >= command.mono_time), None)
    if later:
      delays.append((later.mono_time - command.mono_time) / 1e9)
  return result("check_control_command_response", "ok", metrics={"samples": len(delays), "max_response_alignment_s": max(delays, default=0.0)}, evidence=[create_evidence("control_response_alignment", "Matched carControl messages to next carState observations.", "check_control_command_response", metrics={"max_alignment_s": max(delays, default=0.0)})])


def check_carcontrol_sendcan_consistency(case: DiagnosticCase) -> ToolResult:
  return find_first_divergence(case, "carControl", "sendcan")


def check_sendcan_vehicle_state_consistency(case: DiagnosticCase) -> ToolResult:
  return find_first_divergence(case, "sendcan", "carState", max_delay_s=0.3)
