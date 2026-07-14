from __future__ import annotations

from collections import Counter
from statistics import median

from zhijia_guardian.schema.models import ADSMessage, DiagnosticCase, TimeRange, ToolResult
from .evidence import create_evidence, result


def extract_can_frames(case: DiagnosticCase, topic: str = "can") -> list[tuple[int, dict]]:
  frames = []
  for message in case.messages:
    if message.topic == topic:
      frames.extend((message.mono_time, frame) for frame in message.payload_summary.get("frames", []))
  return frames


def summarize_can_addresses(case: DiagnosticCase, topic: str = "can") -> ToolResult:
  frames = extract_can_frames(case, topic)
  if not frames:
    return result("summarize_can_addresses", "insufficient_observability", limitations=[f"{topic} frames unavailable"])
  addresses = Counter(str(frame.get("address")) for _, frame in frames)
  buses = Counter(str(frame.get("bus")) for _, frame in frames)
  evidence = create_evidence("can_address_summary", f"Observed {len(addresses)} CAN addresses in {topic}.", "summarize_can_addresses", topic=topic, metrics={"addresses": dict(addresses), "buses": dict(buses)})
  return result("summarize_can_addresses", "ok", metrics={"addresses": dict(addresses), "buses": dict(buses)}, evidence=[evidence])


def calculate_can_address_frequency(case: DiagnosticCase, topic: str = "can") -> ToolResult:
  frames = extract_can_frames(case, topic)
  by_addr: dict[str, list[int]] = {}
  for timestamp, frame in frames:
    by_addr.setdefault(str(frame.get("address")), []).append(timestamp)
  metrics = {address: round((len(times) - 1) / ((times[-1] - times[0]) / 1e9), 3) for address, times in by_addr.items() if len(times) > 1 and times[-1] > times[0]}
  if not metrics:
    return result("calculate_can_address_frequency", "insufficient_observability", limitations=["not enough repeated CAN frames"])
  return result("calculate_can_address_frequency", "ok", metrics={"frequency_hz": metrics}, evidence=[create_evidence("can_frequency", "Calculated CAN-address frequencies.", "calculate_can_address_frequency", topic=topic, metrics=metrics)])


def detect_can_gaps(case: DiagnosticCase, topic: str = "can", multiplier: float = 3.0) -> ToolResult:
  timestamps = sorted({time for time, _ in extract_can_frames(case, topic)})
  if len(timestamps) < 3:
    return result("detect_can_gaps", "insufficient_observability", limitations=[f"insufficient {topic} samples"])
  deltas = [(b-a)/1e9 for a, b in zip(timestamps, timestamps[1:])]
  base = median(deltas)
  hits = [(timestamps[i], timestamps[i+1], delta) for i, delta in enumerate(deltas) if delta > base * multiplier]
  evidence = [create_evidence("can_gap", f"{topic} frame gap {delta:.3f}s exceeds {multiplier}× median.", "detect_can_gaps", topic=topic, time_window=TimeRange(start_ns=a, end_ns=b), metrics={"gap_s": delta, "median_s": base}) for a,b,delta in hits]
  return result("detect_can_gaps", "ok", metrics={"gap_count": len(hits), "median_interval_s": base}, evidence=evidence)
