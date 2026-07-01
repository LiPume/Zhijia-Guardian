from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from zhijia_guardian.schemas.diagnosis import EvidenceRecord
from zhijia_guardian.schemas.scenario import Detection, FrameRecord, ScenarioRecord
from zhijia_guardian.tools.evidence import EvidenceFactory
from zhijia_guardian.utils.geometry import euclidean_distance


class PerceptionEvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missed_key_actors: int = 0
    false_positives: int = 0
    class_confusions: int = 0
    confidence_drop_events: int = 0
    evidence: list[EvidenceRecord] = Field(default_factory=list)


def evaluate_perception(
    scenario: ScenarioRecord,
    factory: EvidenceFactory | None = None,
    match_distance: float = 2.5,
    confidence_threshold: float = 0.35,
    confidence_drop: float = 0.35,
) -> PerceptionEvalResult:
    factory = factory or EvidenceFactory()
    missed = 0
    false_positive = 0
    confusion = 0
    confidence_drop_events = 0
    miss_time: float | None = None
    fp_time: float | None = None
    confusion_time: float | None = None
    confidence_time: float | None = None
    confidence_by_track: dict[str, list[tuple[float, float, float | None, bool]]] = {}

    for frame in scenario.frames:
        if not frame.perception.available:
            continue
        matches = _match_frame(frame, match_distance)
        matched_detection_ids = {id(det) for _, det, _ in matches if det is not None}

        for actor, detection, distance in matches:
            if detection is None:
                if actor.is_key_actor:
                    missed += 1
                    miss_time = miss_time if miss_time is not None else frame.timestamp
                continue
            if detection.type != actor.type:
                confusion += 1
                confusion_time = confusion_time if confusion_time is not None else frame.timestamp
            if actor.is_key_actor and detection.confidence < confidence_threshold:
                missed += 1
                miss_time = miss_time if miss_time is not None else frame.timestamp
            confidence_by_track.setdefault(detection.track_id, []).append(
                (
                    frame.timestamp,
                    detection.confidence,
                    _bbox_area(detection.bbox_xyxy),
                    actor.is_key_actor,
                )
            )

        for detection in frame.perception.detections:
            if id(detection) not in matched_detection_ids:
                false_positive += 1
                fp_time = fp_time if fp_time is not None else frame.timestamp

    for values in confidence_by_track.values():
        drop_time = _persistent_confidence_drop(values, confidence_drop)
        if drop_time is not None:
            confidence_drop_events += 1
            confidence_time = confidence_time if confidence_time is not None else drop_time

    evidence: list[EvidenceRecord] = []
    if missed:
        evidence.append(
            factory.make(
                "PER",
                "missed_key_actors",
                missed,
                0,
                miss_time,
                "violation",
                supports=["perception_miss"],
                contradicts=["normal"],
                description="Key actor is missing or below confidence threshold in perception output.",
            )
        )
    if false_positive:
        evidence.append(
            factory.make(
                "PER",
                "false_positives",
                false_positive,
                0,
                fp_time,
                "violation",
                supports=["perception_false_positive"],
                contradicts=["normal"],
                description="Detection exists without a nearby annotated actor.",
            )
        )
    if confusion:
        evidence.append(
            factory.make(
                "PER",
                "class_confusions",
                confusion,
                0,
                confusion_time,
                "violation",
                supports=["perception_class_confusion"],
                contradicts=["normal"],
                description="Matched detection class differs from actor class.",
            )
        )
    if confidence_drop_events:
        evidence.append(
            factory.make(
                "PER",
                "confidence_drop_events",
                confidence_drop_events,
                confidence_drop,
                confidence_time,
                "violation",
                supports=["perception_confidence_drop"],
                contradicts=["normal"],
                description="Detection confidence drops sharply over time.",
            )
        )
    if not evidence and any(frame.perception.available for frame in scenario.frames):
        evidence.append(
            factory.make(
                "PER",
                "perception_anomalies",
                0,
                0,
                scenario.frames[0].timestamp,
                "normal",
                supports=["normal"],
                contradicts=["perception_miss", "perception_false_positive", "perception_confidence_drop"],
                description="No perception miss, false positive, or confidence drop detected.",
            )
        )
    return PerceptionEvalResult(
        missed_key_actors=missed,
        false_positives=false_positive,
        class_confusions=confusion,
        confidence_drop_events=confidence_drop_events,
        evidence=evidence,
    )


def _match_frame(frame: FrameRecord, match_distance: float) -> list[tuple[object, Detection | None, float | None]]:
    matches = []
    available = list(frame.perception.detections)
    for actor in frame.actors_gt:
        explicit_index = next(
            (
                index
                for index, detection in enumerate(available)
                if detection.matched_gt_id == actor.actor_id
            ),
            None,
        )
        if explicit_index is not None:
            matches.append((actor, available.pop(explicit_index), 0.0))
            continue
        best_index: int | None = None
        best_distance: float | None = None
        for index, detection in enumerate(available):
            if detection.x is None or detection.y is None:
                continue
            distance = euclidean_distance(actor.x, actor.y, detection.x, detection.y)
            if best_distance is None or distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is None or best_distance is None or best_distance > match_distance:
            matches.append((actor, None, None))
        else:
            matches.append((actor, available.pop(best_index), best_distance))
    return matches


def _bbox_area(bbox: tuple[float, float, float, float] | None) -> float | None:
    if bbox is None:
        return None
    return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


def _persistent_confidence_drop(
    values: list[tuple[float, float, float | None, bool]],
    drop_threshold: float,
    min_consecutive: int = 2,
    min_area_ratio: float = 0.6,
) -> float | None:
    if len(values) < min_consecutive + 1:
        return None
    for start in range(1, len(values) - min_consecutive + 1):
        baseline = max(values[:start], key=lambda item: item[1])
        low_values = values[start : start + min_consecutive]
        if not all(item[3] for item in low_values):
            continue
        if not all(baseline[1] - item[1] >= drop_threshold for item in low_values):
            continue
        baseline_area = baseline[2]
        if baseline_area is not None and not all(
            item[2] is not None and item[2] >= baseline_area * min_area_ratio
            for item in low_values
        ):
            continue
        return low_values[0][0]
    return None
