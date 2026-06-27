from math import pi

import pytest

from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    ActorState,
    EgoState,
    FrameRecord,
    MetaInfo,
    ScenarioRecord,
    SourceInfo,
)
from zhijia_guardian.tools.ttc import compute_ttc


def _scenario(ego: EgoState, actors: list[ActorState]) -> ScenarioRecord:
    return ScenarioRecord(
        scenario_id="ttc_rotation_000001",
        source=SourceInfo(dataset="test", version="v0"),
        meta=MetaInfo(frequency_hz=10.0, duration=0.0),
        frames=[
            FrameRecord(
                timestamp=0.0,
                ego=ego,
                actors_gt=actors,
                actors_gt_source=ActorGtSource.SIMULATION,
            )
        ],
    )


def test_ttc_uses_ego_heading_in_world_coordinates():
    record = _scenario(
        EgoState(x=0.0, y=0.0, yaw=pi / 2.0, vx=0.0, vy=10.0),
        [ActorState(actor_id="ahead", type="vehicle", x=0.0, y=20.0, vx=0.0, vy=0.0)],
    )

    result = compute_ttc(record)

    assert result.min_ttc == pytest.approx(2.0)
    assert result.min_ttc_time == pytest.approx(0.0)


def test_ttc_ignores_actor_outside_ego_local_lateral_gate():
    record = _scenario(
        EgoState(x=0.0, y=0.0, yaw=pi / 2.0, vx=0.0, vy=10.0),
        [ActorState(actor_id="adjacent", type="vehicle", x=4.0, y=20.0, vx=0.0, vy=0.0)],
    )

    result = compute_ttc(record)

    assert result.min_ttc is None
    assert result.points[0].ttc is None
