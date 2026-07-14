from __future__ import annotations

import json
import math
from pathlib import Path

from zhijia_guardian.schema.models import ADSMessage, DiagnosticCase, SourceInfo, TimeRange


DEPENDENCIES = {
  "longitudinalPlan": ["controlsState", "carControl"],
  "controlsState": ["carControl"],
  "carControl": ["sendcan"],
  "sendcan": ["carState"],
  "pandaStates": ["sendcan"],
}


def generate_clean_case(case_id: str = "synthetic-openpilot-clean", duration_s: float = 10.0, hz: int = 10) -> DiagnosticCase:
  start = 1_000_000_000
  messages: list[ADSMessage] = []
  seq: dict[str, int] = {}

  def add(topic: str, t: float, payload: dict) -> None:
    seq[topic] = seq.get(topic, 0) + 1
    messages.append(ADSMessage(topic=topic, mono_time=start + int(t * 1e9), sequence=seq[topic] - 1, payload_summary=payload,
                               raw_reference=f"synthetic://{topic}/{seq[topic] - 1}"))

  for i in range(int(duration_s * hz)):
    t = i / hz
    accel = 0.25 if t < 5 else -0.12
    speed = 12.0 + 0.7 * math.sin(t / 2)
    add("carState", t, {"vEgo": round(speed, 3), "steeringAngleDeg": round(1.2 * math.sin(t), 3)})
    add("controlsState", t, {"enabled": True, "state": "enabled"})
    add("carControl", t, {"actuators": {"accel": accel, "torque": round(0.1 * math.sin(t), 3)}})
    add("sendcan", t + 0.01, {"frames": [{"address": 0x2E4, "bus": 0, "dat": "0000000000000000"}, {"address": 0x194, "bus": 0, "dat": "0000000000000000"}]})
    if i % 5 == 0:
      add("longitudinalPlan", t, {"aTarget": accel, "vTarget": speed})
    if i % 5 == 0:
      add("can", t + 0.005, {"frames": [{"address": 0x180, "bus": 0, "dat": "0000000000000000"}, {"address": 0x2A0, "bus": 1, "dat": "0000000000000000"}]})
    if i % 10 == 0:
      add("pandaStates", t, {"controlsAllowed": True, "safetyTxBlocked": False, "faults": [], "busOff": False})
  end = max(m.mono_time for m in messages)
  return DiagnosticCase(case_id=case_id, source=SourceInfo(dataset="generated-openpilot-like", route_id="synthetic-route", segment_id="0", is_synthetic=True),
                        time_range=TimeRange(start_ns=start, end_ns=end), messages=messages, dependency_graph=DEPENDENCIES,
                        service_catalog={topic: {"present": True} for topic in seq}, oracle={"visible_to_agents": False, "fault": None})


def inject_perturbation(clean: DiagnosticCase, kind: str = "sendcan_gap", topic: str = "sendcan", start_s: float = 4.0, end_s: float = 5.2) -> tuple[DiagnosticCase, dict]:
  case = clean.model_copy(deep=True)
  start_ns = case.time_range.start_ns + int(start_s * 1e9)
  end_ns = case.time_range.start_ns + int(end_s * 1e9)
  before = len(case.messages)
  if kind == "sendcan_gap":
    case.messages = [m for m in case.messages if not (m.topic == topic and start_ns <= m.mono_time <= end_ns)]
  elif kind == "topic_delay":
    for msg in case.messages:
      if msg.topic == topic and start_ns <= msg.mono_time <= end_ns:
        msg.mono_time += int(0.45 * 1e9)
        msg.quality_flags.append("synthetic_delay")
  else:
    raise ValueError(f"unsupported perturbation: {kind}")
  case.messages.sort(key=lambda m: m.mono_time)
  case.case_id = clean.case_id.replace("clean", "perturbed")
  manifest = {"type": kind, "topic": topic, "start_ns": start_ns, "end_ns": end_ns, "removed_messages": before - len(case.messages), "is_synthetic": True}
  case.oracle = {"visible_to_agents": False, "injected_fault": manifest}
  return case, manifest


def save_case_json(case: DiagnosticCase, path: Path) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(case.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_case_json(path: str | Path) -> DiagnosticCase:
  return DiagnosticCase.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
