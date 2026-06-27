from pathlib import Path

import pytest

from zhijia_guardian.adapters import NuPlanAdapter
from zhijia_guardian.benchmarks import build_nuplan_perturbation_records
from zhijia_guardian.graph import run_diagnosis_graph
from zhijia_guardian.schemas.scenario import TrajectorySource
from zhijia_guardian.tools.planning_eval import evaluate_planning


NUPLAN_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini")


@pytest.mark.skipif(not NUPLAN_ROOT.exists(), reason="nuPlan mini data not found")
def test_nuplan_perturbation_pairs_are_opaque_and_diagnosable():
    records = build_nuplan_perturbation_records(
        NuPlanAdapter(NUPLAN_ROOT),
        pair_count=2,
        seed=42,
    )
    assert len(records) == 4
    labels = []
    pair_labels: dict[str, set[str]] = {}
    for record in records:
        oracle = record.load_oracle_for_eval()
        assert oracle is not None and oracle.fault_type is not None
        labels.append(oracle.fault_type)
        observed = record.observed_view()
        assert "oracle" not in observed
        assert "generation" not in observed["source"]
        assert oracle.fault_type not in record.scenario_id
        assert all(
            frame.planning.trajectory_source == TrajectorySource.PERTURBED_PLANNER
            for frame in record.frames
            if frame.planning.available
        )
        pair_key = str(record.source.generation["pair_key"])
        pair_labels.setdefault(pair_key, set()).add(oracle.fault_type)
        collision_count = evaluate_planning(record).trajectory_collision_count
        assert (collision_count > 0) == (oracle.fault_type == "planning_collision_risk")
        _, diagnosis = run_diagnosis_graph(record)
        assert diagnosis.predicted_fault_type == oracle.fault_type

    assert labels.count("normal") == 2
    assert labels.count("planning_collision_risk") == 2
    assert all(value == {"normal", "planning_collision_risk"} for value in pair_labels.values())
