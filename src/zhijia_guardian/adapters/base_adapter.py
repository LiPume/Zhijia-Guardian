from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from zhijia_guardian.schemas.scenario import ScenarioRecord
from zhijia_guardian.utils.io import dump_scenario_record


class BaseAdapter(ABC):
    @abstractmethod
    def list_scenarios(self) -> list[str]:
        ...

    @abstractmethod
    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        ...

    def export_json(self, scenario_id: str, output_path: str | Path) -> None:
        dump_scenario_record(self.load_scenario(scenario_id), output_path)
