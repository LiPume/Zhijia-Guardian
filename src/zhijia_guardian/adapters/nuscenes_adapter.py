from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zhijia_guardian.adapters.base_adapter import BaseAdapter
from zhijia_guardian.schemas.scenario import (
    ActorGtSource,
    ActorState,
    ControlState,
    EgoState,
    EventRecord,
    FrameRecord,
    MapState,
    MetaInfo,
    PerceptionState,
    PlanningState,
    ScenarioRecord,
    SourceInfo,
)
from zhijia_guardian.utils.geometry import yaw_from_quaternion_wxyz


class NuScenesAdapter(BaseAdapter):
    """Minimal metadata-only nuScenes adapter.

    It maps nuScenes annotations to actors_gt and deliberately leaves
    perception/planning/control unavailable unless detector outputs are added
    by a later adapter stage.
    """

    def __init__(
        self,
        metadata_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini",
        version: str = "v1.0-mini",
    ):
        self.metadata_root = Path(metadata_root)
        self.version = version
        if not self.metadata_root.exists():
            raise FileNotFoundError(self.metadata_root)
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._by_token: dict[str, dict[str, dict[str, Any]]] = {}
        self._load_tables()

    def _load_tables(self) -> None:
        for name in [
            "scene",
            "sample",
            "sample_data",
            "ego_pose",
            "sample_annotation",
            "instance",
            "category",
            "calibrated_sensor",
            "sensor",
        ]:
            path = self.metadata_root / f"{name}.json"
            with path.open("r", encoding="utf-8") as f:
                rows = json.load(f)
            self._tables[name] = rows
            self._by_token[name] = {row["token"]: row for row in rows if "token" in row}

        self._annotations_by_sample: dict[str, list[dict[str, Any]]] = {}
        for ann in self._tables["sample_annotation"]:
            self._annotations_by_sample.setdefault(ann["sample_token"], []).append(ann)

        self._sample_data_by_sample: dict[str, list[dict[str, Any]]] = {}
        for sample_data in self._tables["sample_data"]:
            self._sample_data_by_sample.setdefault(sample_data["sample_token"], []).append(sample_data)

    def list_scenarios(self) -> list[str]:
        return [f"nuscenes_mini_{i + 1:06d}" for i, _ in enumerate(self._tables["sample"])]

    def _sample_for_id(self, scenario_id: str) -> dict[str, Any]:
        prefix = "nuscenes_mini_"
        if scenario_id.startswith(prefix):
            index = int(scenario_id.removeprefix(prefix)) - 1
            try:
                return self._tables["sample"][index]
            except IndexError as exc:
                raise KeyError(scenario_id) from exc
        if scenario_id in self._by_token["sample"]:
            return self._by_token["sample"][scenario_id]
        raise KeyError(scenario_id)

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        sample = self._sample_for_id(scenario_id)
        sample_token = sample["token"]
        lidar_top = self._find_lidar_top_sample_data(sample_token)
        ego_pose = self._by_token["ego_pose"][lidar_top["ego_pose_token"]]

        actors = self._actors_for_sample(sample_token)
        frame = FrameRecord(
            timestamp=0.0,
            ego=EgoState(
                x=ego_pose["translation"][0],
                y=ego_pose["translation"][1],
                yaw=yaw_from_quaternion_wxyz(ego_pose["rotation"]),
            ),
            actors_gt=actors,
            actors_gt_source=ActorGtSource.DATASET_ANNOTATION if actors else ActorGtSource.UNAVAILABLE,
            perception=PerceptionState(available=False),
            planning=PlanningState(available=False),
            control=ControlState(available=False),
            map=MapState(available=False),
        )

        scene = self._scene_for_sample(sample)
        events = [
            EventRecord(
                event_type="dataset_context",
                timestamp=0.0,
                description="nuScenes metadata-only sample; detector media not decoded",
                attributes={"scene_name": scene.get("name"), "sample_token": sample_token},
            )
        ]
        return ScenarioRecord(
            scenario_id=scenario_id,
            source=SourceInfo(
                dataset="nuscenes",
                version=self.version,
                raw_log_id=scene.get("name"),
                raw_tokens={
                    "scene_token": scene.get("token"),
                    "sample_token": sample_token,
                    "lidar_sample_data_token": lidar_top["token"],
                    "ego_pose_token": lidar_top["ego_pose_token"],
                },
            ),
            meta=MetaInfo(
                coordinate_frame="world",
                frequency_hz=2.0,
                duration=0.0,
            ),
            frames=[frame],
            events_observed=events,
            oracle=None,
        )

    def _find_lidar_top_sample_data(self, sample_token: str) -> dict[str, Any]:
        for sample_data in self._sample_data_by_sample.get(sample_token, []):
            calibrated = self._by_token["calibrated_sensor"][sample_data["calibrated_sensor_token"]]
            sensor = self._by_token["sensor"][calibrated["sensor_token"]]
            if sample_data.get("is_key_frame") and sensor.get("channel") == "LIDAR_TOP":
                return sample_data
        raise KeyError(f"LIDAR_TOP sample_data not found for sample {sample_token}")

    def _actors_for_sample(self, sample_token: str) -> list[ActorState]:
        actors: list[ActorState] = []
        for ann in self._annotations_by_sample.get(sample_token, []):
            instance = self._by_token["instance"][ann["instance_token"]]
            category = self._by_token["category"][instance["category_token"]]
            translation = ann["translation"]
            size = ann["size"]
            actors.append(
                ActorState(
                    actor_id=ann["instance_token"],
                    type=category["name"],
                    x=translation[0],
                    y=translation[1],
                    yaw=yaw_from_quaternion_wxyz(ann["rotation"]),
                    length=size[1],
                    width=size[0],
                    height=size[2],
                )
            )
        return actors

    def _scene_for_sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        token = sample["scene_token"]
        return self._by_token["scene"].get(token, {})
