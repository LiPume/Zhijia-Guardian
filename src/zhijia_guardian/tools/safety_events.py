from __future__ import annotations

from zhijia_guardian.schema.models import DiagnosticCase, ToolResult
from .evidence import create_evidence, result
from .message_flow import extract_topic_messages


def extract_panda_safety_events(case: DiagnosticCase) -> ToolResult:
  messages = extract_topic_messages(case, "pandaStates")
  if not messages:
    return result("extract_panda_safety_events", "insufficient_observability", limitations=["pandaStates unavailable"])
  hits = []
  for message in messages:
    payload = message.payload_summary
    if payload.get("controlsAllowed") is False or payload.get("safetyTxBlocked") is True or payload.get("faults") or payload.get("busOff"):
      hits.append(message)
  evidence = [create_evidence("safety_event", "Observed safety/vehicle-interface condition in pandaStates.", "extract_panda_safety_events", topic="pandaStates", metrics=message.payload_summary) for message in hits]
  return result("extract_panda_safety_events", "ok", metrics={"message_count": len(messages), "event_count": len(hits)}, evidence=evidence)


def extract_onroad_events(case: DiagnosticCase) -> ToolResult:
  messages = extract_topic_messages(case, "onroadEvents")
  if not messages:
    return result("extract_onroad_events", "insufficient_observability", limitations=["onroadEvents unavailable"])
  evidence = [create_evidence("onroad_event", "Observed onroad event message.", "extract_onroad_events", topic="onroadEvents", metrics=message.payload_summary) for message in messages if message.payload_summary.get("events")]
  return result("extract_onroad_events", "ok", metrics={"message_count": len(messages), "event_count": len(evidence)}, evidence=evidence)
