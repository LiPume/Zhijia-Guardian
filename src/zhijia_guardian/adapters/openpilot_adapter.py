from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from zhijia_guardian.schema.models import ADSMessage, DiagnosticCase, SourceInfo, TimeRange


def _summary(event: Any, topic: str) -> dict[str, Any]:
  value = getattr(event, topic)
  if topic in {"can", "sendcan"}:
    frames = []
    for frame in value[:200]:
      frames.append({"address": int(frame.address), "bus": int(frame.src), "dat": bytes(frame.dat).hex()})
    return {"frames": frames, "frame_count": len(value)}
  if topic == "carState":
    return {k: getattr(value, k) for k in ("vEgo", "aEgo", "steeringAngleDeg", "standstill") if hasattr(value, k)}
  if topic == "carControl":
    actuators = getattr(value, "actuators", None)
    return {"enabled": getattr(value, "enabled", None), "actuators": {k: getattr(actuators, k) for k in ("accel", "torque", "steer") if actuators is not None and hasattr(actuators, k)}}
  if topic == "controlsState":
    return {k: str(getattr(value, k)) for k in ("enabled", "state") if hasattr(value, k)}
  if topic == "pandaStates":
    return {"count": len(value), "controlsAllowed": [bool(x.controlsAllowed) for x in value if hasattr(x, "controlsAllowed")]}
  if topic == "onroadEvents":
    return {"events": [str(x.name) for x in value]}
  return {"repr": str(value)[:500]}


def load_openpilot_log(path: str | Path, *, openpilot_root: str | Path | None = None, case_id: str | None = None) -> DiagnosticCase:
  """Read one local rlog/qlog with upstream LogReader; no upstream code is modified."""
  root = Path(openpilot_root or os.environ.get("OPENPILOT_ROOT", ""))
  if not root.exists():
    raise RuntimeError("OPENPILOT_ROOT is required for real rlog/qlog parsing; install the optional [openpilot] dependencies")
  if str(root) not in sys.path:
    sys.path.insert(0, str(root))
  # Current openpilot resolves cereal schemas through the shallow opendbc submodule.
  opendbc_root = root / "opendbc_repo"
  if opendbc_root.exists() and str(opendbc_root) not in sys.path:
    sys.path.insert(0, str(opendbc_root))
  try:
    from openpilot.tools.lib.logreader import LogReader
  except ImportError as exc:
    raise RuntimeError("cannot import upstream LogReader; run `pip install -e .[openpilot]`") from exc
  records: list[ADSMessage] = []
  sequence: dict[str, int] = {}
  for event in LogReader(str(path), sort_by_time=True, only_union_types=True):
    topic = event.which()
    sequence[topic] = sequence.get(topic, 0) + 1
    records.append(ADSMessage(topic=topic, mono_time=int(event.logMonoTime), sequence=sequence[topic] - 1, payload_summary=_summary(event, topic),
                              raw_reference=f"{Path(path).name}#{sequence[topic] - 1}"))
  if not records:
    raise RuntimeError("log contained no union messages")
  return DiagnosticCase(case_id=case_id or Path(path).stem, source=SourceInfo(dataset="openpilot-log", source_path=str(path)),
                        time_range=TimeRange(start_ns=min(m.mono_time for m in records), end_ns=max(m.mono_time for m in records)), messages=records,
                        service_catalog={topic: {"count": count} for topic, count in sequence.items()})


def summarize_log_metadata(case: DiagnosticCase) -> dict[str, Any]:
  return {"case_id": case.case_id, "is_synthetic": case.source.is_synthetic, "message_count": len(case.messages), "topics": sorted({m.topic for m in case.messages}), "duration_s": case.time_range.duration_s}
