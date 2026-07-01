#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.adapters import ManualAdapter  # noqa: E402
from zhijia_guardian.graph import DiagnosisGraph  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect one deterministic multi-agent diagnosis run.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--scenario-id", help="Defaults to the first scenario in sorted order.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    adapter = ManualAdapter(args.dataset)
    scenario_ids = adapter.list_scenarios()
    if not scenario_ids:
        raise SystemExit(f"No canonical scenarios found under {args.dataset}")
    scenario_id = args.scenario_id or scenario_ids[0]
    scenario = adapter.load_scenario(scenario_id)
    graph = DiagnosisGraph()
    state = graph.invoke(scenario)
    diagnosis = state.diagnosis
    if diagnosis is None:
        raise RuntimeError("diagnosis graph did not produce a diagnosis")

    payload = {
        "scenario_id": scenario_id,
        "topology": graph.describe(),
        "executed_nodes": state.executed_nodes,
        "module_diagnoses": {
            name: item.model_dump(mode="json", exclude={"evidence"})
            for name, item in state.module_diagnoses.items()
        },
        "prediction": {
            "fault_type": diagnosis.predicted_fault_type,
            "root_module": diagnosis.predicted_root_module,
            "fault_start_time": diagnosis.predicted_fault_start_time,
            "confidence": diagnosis.confidence,
            "evidence_ids": diagnosis.candidate_root_causes[0].evidence_ids
            if diagnosis.candidate_root_causes
            else [],
        },
        "agent_trace": [step.model_dump(mode="json") for step in diagnosis.agent_trace],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
