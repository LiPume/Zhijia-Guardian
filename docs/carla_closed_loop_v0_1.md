# CARLA Closed-loop Benchmark v0.1

## 目标

离线注入只修改已有日志，不能证明故障会改变车辆动力学。本 benchmark 在 CARLA 0.9.15 中
从相同出生点重新运行 normal、control-delay 和 planning-fault 三种模式，记录真实 ego 状态、
规划轨迹、控制命令、碰撞事件和 oracle。

它使用轻量跟车/停车控制器验证诊断链路，不代表复现了完整量产 ADS。

## 场景设计

- 地图：`Town10HD_Opt`。
- 5 个不同父出生点，每个父场景运行 3 种模式，共 15 条。
- ego 初速度：7 m/s；关键前车初始距离：18 m。
- 固定步长：0.1 秒。
- parent-group exclusive split：train 9、val 3、test 3。

三种模式：

| Case | Planner | Control | 物理结果 |
| --- | --- | --- | --- |
| normal | 安全停车轨迹 | TTC 首次低于 1.5 秒时制动 | 5/5 无碰撞 |
| control_delay | 安全停车轨迹 | 风险出现后延迟 0.8 秒制动 | 5/5 碰撞 |
| planning_collision_risk | 0.5 秒后输出穿过前车预测位置的轨迹 | 执行危险规划，不制动 | 5/5 碰撞 |

oracle、case、parent group 和 split 仅在 labels manifest 中。诊断日志文件名和 scenario ID
使用 `carla_cl_v0_1_XXXXXX`，不包含故障标签。

## 时间语义修正

闭环数据要求证据时间表示故障首次出现，而不是最严重时刻：

- TTC 严重度仍记录 `min_ttc`，Control 风险起点改为 TTC 首次跌破 1.5 秒的时间。
- Planning 严重度仍记录 `min_trajectory_margin`，Planning evidence 改为轨迹首次违反
  0.5 米 collision margin 的时间。

这两个时间分别用于制动延迟和跨模块根因排序。规划故障中，危险轨迹证据约在 0.6 秒出现，
低 TTC/控制无响应约在 1.0 秒出现。

## 复现

启动 CARLA：

```bash
./carla.sh
```

另一个终端记录数据：

```bash
conda run -n yolo python scripts/record_carla_closed_loop_benchmark.py \
  --output-root /data5/lzx_data/Zhijia-Guardian/datasets/carla/closed_loop_v0_1 \
  --parents 5 \
  --seed 42 \
  --clean
```

运行评估：

```bash
conda run -n yolo python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/carla/closed_loop_v0_1/canonical/scenarios.jsonl \
  --run-id carla_closed_loop_v0_1_multi_agent_seed42 \
  --seed 42
```

## 正式结果

数据与评估 commit：`80bacf9`。

### 全量 15 场景

| 方法 | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Rule-only | 0.6667 | 0.5556 | 0.6667 | 1.0000 | 0.0000 |

### Parent-isolated test 3 场景

| 方法 | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Rule-only | 0.6667 | 0.5556 | 0.6667 | 1.0000 | 0.0000 |

Rule-only 将 5 条 planning fault 全部判为 control delay，因为它只比较固定证据权重。Multi-Agent
先由 Planning/Control Agent 独立诊断，再利用危险规划早于控制失效的时间关系恢复 planning 根因。

结果目录：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/carla_closed_loop_v0_1_seed42/
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/carla_closed_loop_v0_1_test_seed42/
```

## 局限

- 只有一种“静止前车”模板和 5 个出生点。
- test split 只有一个父场景、3 条样本，不足以估计置信区间。
- perception 来自 simulation annotation 的合成检测，不是相机 detector。
- 下一版需要加入天气、弯道、行人/切入车辆和多 seed，并让独立 planner/controller 接口替代
  当前轻量控制器。
