from __future__ import annotations

from math import atan2, cos, hypot, sin

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.metrics import MetricSeries
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.tools.evidence import EvidenceFactory


class ComfortEvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_abs_acceleration: float | None = None
    max_abs_acceleration_time: float | None = None
    max_abs_jerk: float | None = None
    max_abs_jerk_time: float | None = None
    max_abs_yaw_rate: float | None = None
    max_abs_yaw_rate_time: float | None = None
    series: list[MetricSeries] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)


def evaluate_comfort(
    scenario: ScenarioRecord,
    factory: EvidenceFactory | None = None,
    acceleration_threshold: float = 4.0,
    jerk_threshold: float = 6.0,
    yaw_rate_threshold: float = 0.7,
) -> ComfortEvalResult:
    factory = factory or EvidenceFactory()
    frames = scenario.frames
    if len(frames) < 2:
        return ComfortEvalResult()

    speed_samples = [(frame.timestamp, hypot(frame.ego.vx, frame.ego.vy)) for frame in frames]
    acceleration_samples = _derive_speed_acceleration(speed_samples)
    if not acceleration_samples:
        acceleration_samples = _reported_longitudinal_acceleration(scenario)
    jerk_samples = _derive_rate(acceleration_samples)
    yaw_rate_samples = _derive_yaw_rate([(frame.timestamp, frame.ego.yaw) for frame in frames])

    accel_peak = _max_abs(acceleration_samples)
    jerk_peak = _max_abs(jerk_samples)
    yaw_peak = _max_abs(yaw_rate_samples)

    evidence: list[EvidenceRecord] = []
    if accel_peak is not None:
        violation = abs(accel_peak[1]) > acceleration_threshold
        evidence.append(
            _comfort_evidence(
                factory=factory,
                metric_name="max_abs_acceleration",
                value=accel_peak[1],
                threshold=acceleration_threshold,
                time=accel_peak[0],
                description=(
                    "Peak ego acceleration exceeds the configured comfort threshold."
                    if violation
                    else "Peak ego acceleration is within the configured comfort threshold."
                ),
                violation=violation,
            )
        )

    if jerk_peak is not None:
        violation = abs(jerk_peak[1]) > jerk_threshold
        evidence.append(
            _comfort_evidence(
                factory=factory,
                metric_name="max_abs_jerk",
                value=jerk_peak[1],
                threshold=jerk_threshold,
                time=jerk_peak[0],
                description=(
                    "Peak ego jerk exceeds the configured comfort threshold."
                    if violation
                    else "Peak ego jerk is within the configured comfort threshold."
                ),
                violation=violation,
            )
        )

    if yaw_peak is not None:
        violation = abs(yaw_peak[1]) > yaw_rate_threshold
        evidence.append(
            _comfort_evidence(
                factory=factory,
                metric_name="max_abs_yaw_rate",
                value=yaw_peak[1],
                threshold=yaw_rate_threshold,
                time=yaw_peak[0],
                description=(
                    "Peak ego yaw rate exceeds the configured comfort threshold."
                    if violation
                    else "Peak ego yaw rate is within the configured comfort threshold."
                ),
                violation=violation,
            )
        )

    return ComfortEvalResult(
        max_abs_acceleration=abs(accel_peak[1]) if accel_peak else None,
        max_abs_acceleration_time=accel_peak[0] if accel_peak else None,
        max_abs_jerk=abs(jerk_peak[1]) if jerk_peak else None,
        max_abs_jerk_time=jerk_peak[0] if jerk_peak else None,
        max_abs_yaw_rate=abs(yaw_peak[1]) if yaw_peak else None,
        max_abs_yaw_rate_time=yaw_peak[0] if yaw_peak else None,
        series=[
            _series("ego_speed", speed_samples),
            _series("ego_longitudinal_acceleration", acceleration_samples),
            _series("ego_jerk", jerk_samples),
            _series("ego_yaw_rate", yaw_rate_samples),
        ],
        evidence=evidence,
    )


def _derive_speed_acceleration(speed_samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return _derive_rate(speed_samples)


def _derive_rate(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    rates: list[tuple[float, float]] = []
    for (t0, v0), (t1, v1) in zip(samples, samples[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        rates.append((t1, (v1 - v0) / dt))
    return rates


def _derive_yaw_rate(yaw_samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    rates: list[tuple[float, float]] = []
    for (t0, yaw0), (t1, yaw1) in zip(yaw_samples, yaw_samples[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        rates.append((t1, _angle_diff(yaw1, yaw0) / dt))
    return rates


def _reported_longitudinal_acceleration(scenario: ScenarioRecord) -> list[tuple[float, float]]:
    samples: list[tuple[float, float]] = []
    for frame in scenario.frames:
        ax = frame.ego.ax
        ay = frame.ego.ay
        if ax == 0.0 and ay == 0.0:
            continue
        yaw = frame.ego.yaw
        samples.append((frame.timestamp, ax * cos(yaw) + ay * sin(yaw)))
    return samples


def _max_abs(samples: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not samples:
        return None
    return max(samples, key=lambda item: abs(item[1]))


def _comfort_evidence(
    factory: EvidenceFactory,
    metric_name: str,
    value: float,
    threshold: float,
    time: float,
    description: str,
    violation: bool = False,
) -> EvidenceRecord:
    return factory.make(
        "COMFORT",
        metric_name,
        round(abs(value), 3),
        threshold,
        time,
        "violation" if violation else "normal",
        supports=[],
        contradicts=[],
        description=description,
    )


def _series(name: str, samples: list[tuple[float, float]]) -> MetricSeries:
    return MetricSeries(
        name=name,
        timestamps=[round(timestamp, 6) for timestamp, _ in samples],
        values=[round(value, 6) for _, value in samples],
    )


def _angle_diff(angle: float, reference: float) -> float:
    return atan2(sin(angle - reference), cos(angle - reference))
