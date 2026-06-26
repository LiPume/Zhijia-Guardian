from __future__ import annotations

from itertools import count

from zhijia_guardian.schemas.diagnosis import EvidenceRecord


class EvidenceFactory:
    def __init__(self) -> None:
        self._counter = count(1)

    def make(
        self,
        prefix: str,
        metric_name: str,
        value: float | bool | str | None,
        threshold: float | None,
        time: float | None,
        status: str,
        supports: list[str] | None = None,
        contradicts: list[str] | None = None,
        description: str = "",
    ) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=f"E_{prefix}_{next(self._counter):03d}",
            metric_name=metric_name,
            value=value,
            threshold=threshold,
            time=time,
            status=status,  # type: ignore[arg-type]
            supports=supports or [],
            contradicts=contradicts or [],
            description=description,
        )
