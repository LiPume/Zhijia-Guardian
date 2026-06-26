# nuPlan Mini Mapping

当前实现：`src/zhijia_guardian/adapters/nuplan_adapter.py`

数据位置：

```text
/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini/
```

## Minimal Join

| nuPlan table | Canonical field |
| --- | --- |
| `scene` | scenario id, roadblock ids, source raw tokens |
| `lidar_pc` | frame sequence anchor |
| `ego_pose` | `frames[*].ego` |
| `lidar_box` | `frames[*].actors_gt` |
| `track -> category` | actor id and actor type |
| `scenario_tag` | `events_observed` context tags |
| `traffic_light_status` | `events_observed` traffic-light context |

## Current Boundary

- nuPlan 不天然提供被测 planner 输出。
- nuPlan 不天然提供控制指令。
- `control.available=false`
- `perception.available=false`
- `actors_gt_source=dataset_annotation`
- 当前 adapter 将专家未来 ego 轨迹写为 `planning.trajectory_source=expert_future`，仅作参考，不参与 planner fault F1。

若后续在 nuPlan 场景骨架上运行离线 planner，设置 `planning.trajectory_source=offline_planner`。若注入危险轨迹，设置 `planning.trajectory_source=perturbed_planner`，oracle 单独提供给 evaluation。
