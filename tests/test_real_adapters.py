from pathlib import Path

import pytest

from zhijia_guardian.adapters import NuPlanAdapter, NuScenesAdapter
from zhijia_guardian.schemas.scenario import ActorGtSource, TrajectorySource


NUSCENES_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini")
NUPLAN_ROOT = Path("/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini")


@pytest.mark.skipif(not NUSCENES_ROOT.exists(), reason="nuScenes mini metadata not found")
def test_nuscenes_adapter_smoke():
    adapter = NuScenesAdapter(NUSCENES_ROOT)
    scenario_id = adapter.list_scenarios()[0]
    record = adapter.load_scenario(scenario_id)
    assert record.source.dataset == "nuscenes"
    assert record.oracle is None
    assert "oracle" not in record.observed_view()
    assert len(record.frames) == 1
    frame = record.frames[0]
    assert frame.actors_gt_source in {ActorGtSource.DATASET_ANNOTATION, ActorGtSource.UNAVAILABLE}
    assert frame.perception.available is False
    assert frame.planning.available is False
    assert frame.control.available is False


@pytest.mark.skipif(not NUPLAN_ROOT.exists(), reason="nuPlan mini data not found")
def test_nuplan_adapter_smoke():
    adapter = NuPlanAdapter(NUPLAN_ROOT, max_frames=5)
    scenario_id = adapter.list_scenarios()[0]
    record = adapter.load_scenario(scenario_id)
    assert record.source.dataset == "nuplan"
    assert record.oracle is None
    assert "oracle" not in record.observed_view()
    assert len(record.frames) >= 1
    frame = record.frames[0]
    assert frame.actors_gt_source in {ActorGtSource.DATASET_ANNOTATION, ActorGtSource.UNAVAILABLE}
    assert frame.perception.available is False
    assert frame.control.available is False
    assert frame.planning.trajectory_source in {TrajectorySource.EXPERT_FUTURE, TrajectorySource.UNAVAILABLE}
