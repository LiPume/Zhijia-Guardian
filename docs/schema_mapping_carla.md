# CARLA 字段映射

## 定位

CARLA 用于生成可控的感知、规划、控制全链路日志及故障 oracle。运行时输出版本化的
`carla_log_v0_1` 原始 JSON，`CarlaAdapter` 再转换成统一 `ScenarioRecord`；tools 和 agents
不导入 `carla`，因此仿真与离线诊断可以解耦。

## 文件边界

```text
raw/logs/000001.json                 # 诊断可见的 CARLA 运行日志
raw/labels/carla_v0_1_000001.label.json  # 仅 evaluation 使用
canonical/scenarios.jsonl            # adapter 合并后的 ScenarioRecord
```

- 原始日志文件名和 `scenario_id` 必须使用不含故障标签的流水号。
- `CarlaAdapter(log_dir)` 不读取任何 oracle。
- 只有 evaluation/export 阶段显式传入 `label_dir` 才合并 oracle；`observed_view()` 仍会剔除 oracle。

## 映射表

| CARLA 原始字段 | Canonical 字段 | 转换 |
| --- | --- | --- |
| `fixed_delta_seconds` | `meta.frequency_hz` | `1 / fixed_delta_seconds` |
| `simulation_time` | `frames[*].timestamp` | 减去首帧时间 |
| actor `transform.location` | ego/actor `x,y` | 保留 CARLA world 坐标，单位米 |
| actor `rotation.yaw` | ego/actor `yaw` | 度转弧度 |
| bounding box `extent.x/y/z` | `length/width/height` | 半尺寸乘 2 |
| world actors | `actors_gt` | `actors_gt_source=simulation` |
| synthetic/model detections | `perception.detections` | 必须标注 `detection_source` |
| planner waypoints | `planning.trajectory` | world 坐标，必须标注 `trajectory_source` |
| `VehicleControl` | `control` | steer/throttle/brake 原值 |
| map waypoint | `map.lane_id/roadblock_ids` | `lane_id=road_id:lane_id` |
| collision/lane invasion callback | `events_observed` | 事件时间对齐首帧 |

## 证据边界

- `actors_gt` 是仿真真值，不代表真实车端天然具有 GT；商业部署时可替换为离线重建或不可用。
- 第一版 perception 可由仿真 annotation 合成，必须写
  `detection_source=synthetic_from_annotation`，不能宣称运行了真实 detector。
- 规则/BehaviorAgent 轨迹写 `offline_planner`，故障注入后的轨迹写 `perturbed_planner`。
- CARLA 左手世界坐标保持不变；yaw 只做单位转换。所有对象共享同一坐标系，几何工具可直接计算。

## 原始日志 v0.1 最小字段

每帧必须包含 `frame_id`、`simulation_time`、ego transform/velocity/acceleration/bounding box。
actors、perception、planning、control、map 和 events 均按可用性显式记录。Pydantic 使用
`extra=forbid` 校验，运行时字段变化必须升级日志版本或同步修改 adapter，避免静默读错数据。

## 第一版生成方式

`scripts/record_carla_base_scenarios.py` 在 CARLA 同步模式下生成跟随静止前车的基础日志：

- ego 与关键前车状态、VehicleControl、地图 waypoint 来自真实 CARLA API；
- collision/lane-invasion 来自 CARLA sensor callback；
- perception 是在 simulation annotation 上加入小位置噪声的合成检测，来源显式标为
  `synthetic_from_annotation`；
- planning 是沿当前车道生成的安全停车 rollout，来源标为 `offline_planner`，不是神经网络 planner；
- 基础场景在低 TTC 时及时制动，供 control-delay 版本保持相同场景骨架做信号级注入。

随后用 `scripts/generate_carla_fault_benchmark.py` 从每个基础日志派生六个成对版本。当前
`injection_scope=offline_signal_level`，即修改感知/规划/控制日志信号，不宣称已经重跑故障后的
车辆动力学。闭环动力学故障注入是下一阶段增强项。
