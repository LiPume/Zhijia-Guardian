# SafeBench Mapping and Feasibility Gate

## 调研版本

- 官方仓库：`trust-ai/SafeBench`。
- 本地只读浅克隆：`/data5/lzx_data/Zhijia-Guardian/third_party/SafeBench`。
- 调研 commit：`dec22690c23fc152d65ddf87ae1fc7f3785c29b8c`。
- 官方推荐运行时：Python 3.8、CARLA 0.9.13。
- 本项目稳定运行时：Python 3.10、CARLA 0.9.15。

SafeBench 官方支持 perception 和 planning/control 场景，并通过 `eval_results/records.pkl` 保存
逐场景记录。该文件是 joblib/pickle，不应在在线诊断进程里直接反序列化。

## 官方 Planning Record 覆盖

| SafeBench frame 字段 | Canonical 字段 | 状态 |
| --- | --- | --- |
| `current_game_time` | `frames[*].timestamp` | 可直接映射 |
| `ego_x/ego_y/ego_yaw` | `frames[*].ego` | 可直接映射，yaw 从 degree 转 radian |
| `ego_velocity` | `ego.vx/vy` | 按 yaw 分解 |
| `ego_acceleration_*` | `ego.ax/ay` | 可直接映射 |
| `collision/off_road/lane_invasion/...` | `events_observed` | 首次失败转事件 |
| actors | `actors_gt` | 官方 record 不提供，`unavailable` |
| planner output | `planning` | 官方 record 不提供，`available=false` |
| control command | `control` | 官方 record 不提供，`available=false` |
| perception output | `perception` | planning record 不提供，`available=false` |

因此 SafeBench 原生 planning record 只能支持 ego 运动和结果事件回放，不能直接用于本项目的
`root_module` 评估。模块信号全缺失时诊断必须输出 `uncertain`，不能把“没有证据”解释为
`normal`。

Perception record 包含 IoU、类别结果和 tensor scores/logits，但不提供 Canonical Schema 当前
要求的世界坐标 detection。第一版 adapter 明确只支持 planning export，不伪造 2D 到世界坐标。

## 安全导出边界

`scripts/export_safebench_records.py` 是离线一次性转换工具：

```bash
python scripts/export_safebench_records.py \
  --records-pkl /trusted/safebench/eval_results/records.pkl \
  --scenario-type-json /path/to/SafeBench/safebench/scenario/config/scenario_type/human.json \
  --safebench-commit dec22690c23fc152d65ddf87ae1fc7f3785c29b8c \
  --carla-version 0.9.13 \
  --output /data5/lzx_data/Zhijia-Guardian/datasets/safebench/records_v0_1.json \
  --trusted-input
```

`--trusted-input` 是强制开关，因为 pickle 加载可能执行代码。主诊断流程只读取导出的严格 JSON。

## 0.9.15 实测结果

2026-06-30 使用现有 CARLA 0.9.15 测试官方 `human` scenario 1 / route 4：

1. SafeBench 可通过少量运行时 shim 在当前 Torch 中导入；官方代码仍引用已删除的
   `torch._six`。
2. 默认 10 秒 CARLA timeout 不足以加载 Town05。
3. 延长 timeout 并预加载 Town05 后，SafeBench 成功解析 10 条配置并进入 `data_id=0`。
4. 创建官方场景 actor 时 CARLA 0.9.15 UE4 进程触发 `SIGSEGV`，未生成 records。

结论：不在 `yolo` 环境里继续强行兼容 SafeBench 0.9.13 runtime，也不下载第二套大型 CARLA。
保留 JSON adapter 和导出 contract；真实闭环根因实验继续使用已稳定的 CARLA 0.9.15 recorder。

## Canonical 输出

`SafeBenchAdapter` 输出：

- opaque ID：`safebench_v0_1_XXXXXX`；
- `actors_gt_source=unavailable`；
- perception/planning/control 均为 `available=false`；
- criteria 首次失败进入 `events_observed`；
- `oracle=None`，因为 SafeBench 场景类型和 collision outcome 不是模块根因标签。

这个 adapter 是格式兼容和失败案例回放入口，不作为 Fault Macro-F1 benchmark。
