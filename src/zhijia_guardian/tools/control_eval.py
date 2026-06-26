from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.evidence import EvidenceFactory


class ControlEvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_start_time: float | None = None
    brake_response_time: float | None = None
    brake_delay: float | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)


def evaluate_control_delay(
    scenario: ScenarioRecord,
    min_ttc_time: float | None,
    min_ttc: float | None,
    factory: EvidenceFactory | None = None,
    ttc_threshold: float = 1.5,
    brake_threshold: float = 0.25,
    max_delay: float = 0.6,
) -> ControlEvalResult:
    factory = factory or EvidenceFactory()
    if min_ttc is None or min_ttc >= ttc_threshold:
        return ControlEvalResult()
    if not any(frame.control.available for frame in scenario.frames):
        return ControlEvalResult(risk_start_time=min_ttc_time)

    risk_start_time = min_ttc_time
    brake_response_time: float | None = None
    for frame in scenario.frames:
        if risk_start_time is None or frame.timestamp < risk_start_time:
            continue
        if frame.control.available and (frame.control.brake or 0.0) >= brake_threshold:
            brake_response_time = frame.timestamp
            break

    brake_delay = None if brake_response_time is None or risk_start_time is None else brake_response_time - risk_start_time
    evidence: list[EvidenceRecord] = []
    if brake_response_time is None or (brake_delay is not None and brake_delay > max_delay):
        evidence.append(
            factory.make(
                "CTRL",
                "brake_delay",
                round(brake_delay, 3) if brake_delay is not None else "no_brake_response",
                max_delay,
                risk_start_time,
                "violation",
                supports=["control_delay"],
                contradicts=["normal"],
                description="Brake command is delayed after low-TTC risk appears.",
            )
        )
    else:
        evidence.append(
            factory.make(
                "CTRL",
                "brake_delay",
                round(brake_delay, 3),
                max_delay,
                risk_start_time,
                "normal",
                supports=["normal"],
                contradicts=["control_delay"],
                description="Brake command responds within allowed delay.",
            )
        )

    return ControlEvalResult(
        risk_start_time=risk_start_time,
        brake_response_time=brake_response_time,
        brake_delay=brake_delay,
        evidence=evidence,
    )
