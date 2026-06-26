from __future__ import annotations

import sqlite3
import zipfile
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
    TrajectoryPoint,
    TrajectorySource,
)
from zhijia_guardian.utils.geometry import token_hex, yaw_from_quaternion_xyzw


class NuPlanAdapter(BaseAdapter):
    """Minimal SQLite nuPlan adapter for schema smoke tests."""

    def __init__(
        self,
        dataset_root: str | Path = "/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini",
        version: str = "v1.1-mini",
        max_frames: int = 20,
        stride: int = 2,
    ):
        self.dataset_root = Path(dataset_root)
        self.version = version
        self.max_frames = max_frames
        self.stride = stride
        if not self.dataset_root.exists():
            raise FileNotFoundError(self.dataset_root)
        self.sample_db_dir = self.dataset_root / "extracted" / "sample_db"
        self.sample_db_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_sample_db()
        self._scenario_index = self._build_scenario_index()

    def _ensure_sample_db(self) -> None:
        if list(self.sample_db_dir.glob("*.db")):
            return
        zip_path = self.dataset_root / "raw" / "nuplan-v1.1_mini.zip"
        if not zip_path.exists():
            raise FileNotFoundError(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            db_infos = [info for info in zf.infolist() if info.filename.endswith(".db")]
            if not db_infos:
                raise FileNotFoundError("no nuPlan db files found in mini zip")
            smallest = min(db_infos, key=lambda info: info.file_size)
            extracted = zf.extract(smallest, self.sample_db_dir)
        Path(extracted).rename(self.sample_db_dir / Path(extracted).name)

    def _db_files(self) -> list[Path]:
        return sorted(self.sample_db_dir.glob("*.db"))

    def _build_scenario_index(self) -> list[dict[str, Any]]:
        index: list[dict[str, Any]] = []
        for db_path in self._db_files():
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT token, name, roadblock_ids FROM scene ORDER BY name").fetchall()
            for row in rows:
                index.append(
                    {
                        "scenario_id": f"nuplan_mini_{len(index) + 1:06d}",
                        "db_path": db_path,
                        "scene_token": bytes(row["token"]),
                        "scene_name": row["name"],
                        "roadblock_ids": row["roadblock_ids"] or "",
                    }
                )
        return index

    def list_scenarios(self) -> list[str]:
        return [item["scenario_id"] for item in self._scenario_index]

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        item = self._find_scenario(scenario_id)
        db_path = Path(item["db_path"])
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            lidar_rows = self._load_lidar_rows(conn, item["scene_token"])
            if not lidar_rows:
                raise ValueError(f"nuPlan scene has no lidar_pc rows: {scenario_id}")
            first_ts = lidar_rows[0]["timestamp"]
            frames = [self._frame_from_lidar_row(conn, row, first_ts, item) for row in lidar_rows]
            events = self._events_for_scene(conn, item["scene_token"], first_ts)

        duration = frames[-1].timestamp - frames[0].timestamp if len(frames) > 1 else 0.0
        return ScenarioRecord(
            scenario_id=scenario_id,
            source=SourceInfo(
                dataset="nuplan",
                version=self.version,
                raw_log_id=db_path.stem,
                raw_tokens={
                    "db_file": str(db_path),
                    "scene_token": token_hex(item["scene_token"]),
                    "scene_name": item["scene_name"],
                },
            ),
            meta=MetaInfo(
                coordinate_frame="world",
                frequency_hz=10.0,
                duration=duration,
            ),
            frames=frames,
            events_observed=events,
            oracle=None,
        )

    def _find_scenario(self, scenario_id: str) -> dict[str, Any]:
        for item in self._scenario_index:
            if item["scenario_id"] == scenario_id:
                return item
        raise KeyError(scenario_id)

    def _load_lidar_rows(self, conn: sqlite3.Connection, scene_token: bytes) -> list[sqlite3.Row]:
        rows = conn.execute(
            """
            SELECT
              lp.token AS lidar_pc_token,
              lp.timestamp AS timestamp,
              lp.ego_pose_token AS ego_pose_token,
              ep.x AS ego_x,
              ep.y AS ego_y,
              ep.qw AS qw,
              ep.qx AS qx,
              ep.qy AS qy,
              ep.qz AS qz,
              ep.vx AS vx,
              ep.vy AS vy,
              ep.acceleration_x AS ax,
              ep.acceleration_y AS ay
            FROM lidar_pc lp
            JOIN ego_pose ep ON ep.token = lp.ego_pose_token
            WHERE lp.scene_token = ?
            ORDER BY lp.timestamp
            """,
            (scene_token,),
        ).fetchall()
        sampled = rows[:: self.stride]
        return sampled[: self.max_frames]

    def _frame_from_lidar_row(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        first_ts: int,
        item: dict[str, Any],
    ) -> FrameRecord:
        timestamp = (row["timestamp"] - first_ts) / 1_000_000.0
        actors = self._actors_for_lidar_pc(conn, row["lidar_pc_token"])
        trajectory = self._expert_future(conn, item["scene_token"], row["timestamp"])
        return FrameRecord(
            timestamp=timestamp,
            ego=EgoState(
                x=row["ego_x"],
                y=row["ego_y"],
                yaw=yaw_from_quaternion_xyzw(row["qx"], row["qy"], row["qz"], row["qw"]),
                vx=row["vx"] or 0.0,
                vy=row["vy"] or 0.0,
                ax=row["ax"] or 0.0,
                ay=row["ay"] or 0.0,
            ),
            actors_gt=actors,
            actors_gt_source=ActorGtSource.DATASET_ANNOTATION if actors else ActorGtSource.UNAVAILABLE,
            perception=PerceptionState(available=False),
            planning=PlanningState(
                available=bool(trajectory),
                trajectory_source=TrajectorySource.EXPERT_FUTURE if trajectory else TrajectorySource.UNAVAILABLE,
                trajectory=trajectory,
                intent="expert_reference" if trajectory else None,
            ),
            control=ControlState(available=False),
            map=MapState(
                available=bool(item["roadblock_ids"]),
                roadblock_ids=item["roadblock_ids"].split() if item["roadblock_ids"] else [],
            ),
        )

    def _actors_for_lidar_pc(self, conn: sqlite3.Connection, lidar_pc_token: bytes) -> list[ActorState]:
        rows = conn.execute(
            """
            SELECT
              lb.token AS box_token,
              lb.x AS x,
              lb.y AS y,
              lb.yaw AS yaw,
              lb.vx AS vx,
              lb.vy AS vy,
              lb.length AS length,
              lb.width AS width,
              lb.height AS height,
              c.name AS category
            FROM lidar_box lb
            JOIN track t ON t.token = lb.track_token
            JOIN category c ON c.token = t.category_token
            WHERE lb.lidar_pc_token = ?
            ORDER BY c.name, lb.token
            """,
            (lidar_pc_token,),
        ).fetchall()
        actors: list[ActorState] = []
        for row in rows:
            actors.append(
                ActorState(
                    actor_id=token_hex(row["box_token"]) or "",
                    type=row["category"],
                    x=row["x"],
                    y=row["y"],
                    yaw=row["yaw"] or 0.0,
                    vx=row["vx"] or 0.0,
                    vy=row["vy"] or 0.0,
                    length=row["length"] or 0.0,
                    width=row["width"] or 0.0,
                    height=row["height"],
                )
            )
        return actors

    def _expert_future(
        self,
        conn: sqlite3.Connection,
        scene_token: bytes,
        timestamp: int,
        horizon_seconds: float = 2.0,
    ) -> list[TrajectoryPoint]:
        end_ts = timestamp + int(horizon_seconds * 1_000_000)
        rows = conn.execute(
            """
            SELECT lp.timestamp AS timestamp, ep.x AS x, ep.y AS y, ep.vx AS vx, ep.vy AS vy
            FROM lidar_pc lp
            JOIN ego_pose ep ON ep.token = lp.ego_pose_token
            WHERE lp.scene_token = ? AND lp.timestamp >= ? AND lp.timestamp <= ?
            ORDER BY lp.timestamp
            """,
            (scene_token, timestamp, end_ts),
        ).fetchall()
        points: list[TrajectoryPoint] = []
        for row in rows[:: max(self.stride, 1)]:
            dt = (row["timestamp"] - timestamp) / 1_000_000.0
            points.append(TrajectoryPoint(dt=dt, x=row["x"], y=row["y"], speed=(row["vx"] ** 2 + row["vy"] ** 2) ** 0.5))
        return points

    def _events_for_scene(
        self,
        conn: sqlite3.Connection,
        scene_token: bytes,
        first_ts: int,
        max_events: int = 20,
    ) -> list[EventRecord]:
        rows = conn.execute(
            """
            SELECT st.type AS type, lp.timestamp AS timestamp, COUNT(*) AS n
            FROM scenario_tag st
            JOIN lidar_pc lp ON lp.token = st.lidar_pc_token
            WHERE lp.scene_token = ?
            GROUP BY st.type, lp.timestamp
            ORDER BY lp.timestamp, st.type
            LIMIT ?
            """,
            (scene_token, max_events),
        ).fetchall()
        events = [
            EventRecord(
                event_type="context_tag",
                timestamp=(row["timestamp"] - first_ts) / 1_000_000.0,
                description=row["type"],
                attributes={"tag": row["type"], "count": row["n"]},
            )
            for row in rows
        ]
        tl_rows = conn.execute(
            """
            SELECT tls.status AS status, lp.timestamp AS timestamp, COUNT(*) AS n
            FROM traffic_light_status tls
            JOIN lidar_pc lp ON lp.token = tls.lidar_pc_token
            WHERE lp.scene_token = ?
            GROUP BY tls.status, lp.timestamp
            ORDER BY lp.timestamp
            LIMIT ?
            """,
            (scene_token, max_events // 2),
        ).fetchall()
        for row in tl_rows:
            events.append(
                EventRecord(
                    event_type="traffic_light_status",
                    timestamp=(row["timestamp"] - first_ts) / 1_000_000.0,
                    description=row["status"],
                    attributes={"status": row["status"], "count": row["n"]},
                )
            )
        return sorted(events, key=lambda event: event.timestamp)
