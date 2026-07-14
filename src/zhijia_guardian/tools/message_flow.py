from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from zhijia_guardian.schema.models import ADSMessage, DiagnosticCase, TimeRange, ToolResult
from .evidence import create_evidence, result


def list_available_topics(case: DiagnosticCase) -> ToolResult:
  counts = Counter(m.topic for m in case.messages)
  evidence = create_evidence("topic_catalog", f"Observed {len(counts)} topics.", "list_available_topics", metrics={"counts": dict(counts)})
  return result("list_available_topics", "ok", metrics={"topics": dict(counts)}, evidence=[evidence])


def extract_topic_messages(case: DiagnosticCase, topic: str) -> list[ADSMessage]:
  return [m for m in case.messages if m.topic == topic]


def calculate_topic_frequency(case: DiagnosticCase, topic: str | None = None) -> ToolResult:
  topics = [topic] if topic else sorted({m.topic for m in case.messages})
  metrics, evidence = {}, []
  for name in topics:
    messages = extract_topic_messages(case, name)
    if len(messages) < 2:
      continue
    duration = (messages[-1].mono_time - messages[0].mono_time) / 1e9
    hz = (len(messages) - 1) / duration if duration else 0.0
    metrics[name] = {"count": len(messages), "frequency_hz": round(hz, 3)}
  if not metrics:
    return result("calculate_topic_frequency", "insufficient_observability", limitations=["fewer than two messages for requested topic"])
  evidence.append(create_evidence("topic_frequency", "Calculated observed topic frequencies.", "calculate_topic_frequency", metrics=metrics))
  return result("calculate_topic_frequency", "ok", metrics=metrics, evidence=evidence)


def detect_message_gaps(case: DiagnosticCase, topic: str, multiplier: float = 3.0) -> ToolResult:
  messages = extract_topic_messages(case, topic)
  if len(messages) < 3:
    return result("detect_message_gaps", "insufficient_observability", limitations=[f"{topic} has fewer than three messages"])
  deltas = [(b.mono_time - a.mono_time) / 1e9 for a, b in zip(messages, messages[1:])]
  baseline = median(deltas)
  indices = [i for i, delta in enumerate(deltas) if baseline > 0 and delta > baseline * multiplier]
  evidence = [create_evidence("message_gap", f"{topic} gap {deltas[i]:.3f}s exceeds {multiplier}× median {baseline:.3f}s.", "detect_message_gaps", topic=topic,
                              time_window=TimeRange(start_ns=messages[i].mono_time, end_ns=messages[i + 1].mono_time), metrics={"gap_s": deltas[i], "median_s": baseline}) for i in indices]
  return result("detect_message_gaps", "ok", metrics={"topic": topic, "median_interval_s": baseline, "gap_count": len(indices)}, evidence=evidence)


def detect_timestamp_discontinuity(case: DiagnosticCase, topic: str | None = None) -> ToolResult:
  messages = [m for m in case.messages if topic is None or m.topic == topic]
  bad = [(a, b) for a, b in zip(messages, messages[1:]) if b.mono_time < a.mono_time]
  evidence = [create_evidence("timestamp_discontinuity", f"Timestamp decreases for {b.topic}.", "detect_timestamp_discontinuity", topic=b.topic,
                              time_window=TimeRange(start_ns=b.mono_time, end_ns=a.mono_time)) for a, b in bad]
  return result("detect_timestamp_discontinuity", "ok", metrics={"count": len(bad)}, evidence=evidence)


def detect_stale_messages(case: DiagnosticCase, topic: str, max_age_s: float = 1.0) -> ToolResult:
  messages = extract_topic_messages(case, topic)
  if not messages:
    return result("detect_stale_messages", "insufficient_observability", limitations=[f"topic {topic} unavailable"])
  age = (case.time_range.end_ns - messages[-1].mono_time) / 1e9
  evidence = [] if age <= max_age_s else [create_evidence("stale_message", f"{topic} is stale by {age:.3f}s at end of case.", "detect_stale_messages", topic=topic, metrics={"age_s": age})]
  return result("detect_stale_messages", "ok", metrics={"age_s": age, "stale": bool(evidence)}, evidence=evidence)


def build_message_dependency_graph(case: DiagnosticCase) -> ToolResult:
  graph = case.dependency_graph or {"longitudinalPlan": ["controlsState", "carControl"], "carControl": ["sendcan"], "sendcan": ["carState"]}
  case.dependency_graph = graph
  evidence = create_evidence("dependency_graph", "Loaded declared message dependency graph.", "build_message_dependency_graph", metrics={"edges": sum(len(v) for v in graph.values())})
  return result("build_message_dependency_graph", "ok", metrics={"graph": graph}, evidence=[evidence])


def slice_time_window(case: DiagnosticCase, start_ns: int, end_ns: int) -> DiagnosticCase:
  return case.model_copy(deep=True, update={"messages": [m for m in case.messages if start_ns <= m.mono_time <= end_ns], "time_range": TimeRange(start_ns=start_ns, end_ns=end_ns)})
