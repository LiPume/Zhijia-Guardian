from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from zhijia_guardian.schemas.scenario import OracleRecord, ScenarioRecord


def load_scenario_record(path: str | Path) -> ScenarioRecord:
    with Path(path).open("r", encoding="utf-8") as f:
        return ScenarioRecord.model_validate(json.load(f))


def dump_scenario_record(record: ScenarioRecord, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(record.model_dump(mode="json", exclude_none=True), f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_scenario_jsonl(path: str | Path) -> list[ScenarioRecord]:
    records: list[ScenarioRecord] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(ScenarioRecord.model_validate(json.loads(stripped)))
    return records


def dump_scenario_jsonl(records: Iterable[ScenarioRecord], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.model_dump(mode="json", exclude_none=True), ensure_ascii=False))
            f.write("\n")


def get_observed_view(record: ScenarioRecord) -> dict:
    return record.observed_view()


def load_oracle(record: ScenarioRecord) -> OracleRecord | None:
    return record.load_oracle_for_eval()
