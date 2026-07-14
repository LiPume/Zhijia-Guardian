"""CARLA-compatible import boundary for normalized ADSLogRecord exports.

This intentionally does not import CARLA. A future recorder may export this compact
message contract from a closed-loop run, which can then use the same active workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

from zhijia_guardian.schema.models import ADSMessage, DiagnosticCase, SourceInfo, TimeRange
from .synthetic_adapter import DEPENDENCIES


def load_carla_adslog_record(path: str | Path) -> DiagnosticCase:
  raw = json.loads(Path(path).read_text(encoding="utf-8"))
  start_ns = int(raw.get("start_ns", 0))
  messages = []
  sequence: dict[str, int] = {}
  for record in raw["records"]:
    topic = record["topic"]
    sequence[topic] = sequence.get(topic, 0) + 1
    mono_time = int(record.get("mono_time", start_ns + int(float(record["timestamp_s"]) * 1e9)))
    messages.append(ADSMessage(topic=topic, mono_time=mono_time, sequence=sequence[topic] - 1, payload_summary=record.get("payload_summary", {}),
      raw_reference=record.get("raw_reference", f"carla://{topic}/{sequence[topic] - 1}"), quality_flags=record.get("quality_flags", [])))
  messages.sort(key=lambda item: item.mono_time)
  if not messages:
    raise ValueError("CARLA ADSLogRecord has no records")
  return DiagnosticCase(case_id=raw.get("case_id", Path(path).stem), source=SourceInfo(stack="carla", dataset="carla-adslog-record", route_id=raw.get("route_id"),
    source_path=str(path), is_synthetic=True), time_range=TimeRange(start_ns=min(item.mono_time for item in messages), end_ns=max(item.mono_time for item in messages)),
    messages=messages, dependency_graph=raw.get("dependency_graph", DEPENDENCIES), service_catalog={topic: {"count": count} for topic, count in sequence.items()}, oracle=raw.get("oracle"))
