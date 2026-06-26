from __future__ import annotations

from pathlib import Path

from zhijia_guardian.adapters.base_adapter import BaseAdapter
from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.utils.io import load_scenario_jsonl, load_scenario_record


class ManualAdapter(BaseAdapter):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(self.root)

    def _files(self) -> list[Path]:
        if self.root.is_file():
            return [self.root]
        return sorted([*self.root.rglob("*.json"), *self.root.rglob("*.jsonl")])

    def list_scenarios(self) -> list[str]:
        scenario_ids: list[str] = []
        for path in self._files():
            if path.suffix == ".jsonl":
                scenario_ids.extend(record.scenario_id for record in load_scenario_jsonl(path))
            else:
                scenario_ids.append(load_scenario_record(path).scenario_id)
        return scenario_ids

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        for path in self._files():
            if path.suffix == ".jsonl":
                for record in load_scenario_jsonl(path):
                    if record.scenario_id == scenario_id:
                        return record
            else:
                record = load_scenario_record(path)
                if record.scenario_id == scenario_id:
                    return record
        raise KeyError(f"manual scenario not found: {scenario_id}")
