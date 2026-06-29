# CARLA Fault Benchmark v0.2

## 目的

CARLA v0.1 的 30 条场景用于验证真实仿真日志到 canonical schema、metrics、agents 和 evaluator
的完整链路，但故障与规则一一对应，Rule-only 和 Multi-Agent 都是满分。v0.2 专门增加三类难度：

1. 随机故障强度和持续时间；
2. 阈值附近但仍属正常的 confidence/planning 边界样本；
3. 上游感知先异常、下游控制后异常的时序复合故障。

v0.2 仍是受控注入 benchmark。它用于验证时序根因排序能力，不等同于自然事故数据上的严格
因果发现。

## 数据构成

- 来源：5 条 CARLA 0.9.15 `Town10HD_Opt` 真实仿真状态日志。
- 每个父日志生成 10 个变体，共 50 条。
- seed：42。
- scenario ID 为不含标签的 `carla_v0_2_XXXXXX`。
- 注入参数、variant、split 和 oracle 仅保存在 `raw/labels/manifest.json`。
- diagnosis observed view 不含 oracle、variant、parent group 或 split。

每个父场景包含：

| Variant | Oracle | 说明 |
| --- | --- | --- |
| normal | normal | 未修改回放 |
| perception_miss | perception_miss | 随机持续帧数的关键目标漏检 |
| perception_false_positive | perception_false_positive | 随机持续帧数的假目标 |
| perception_confidence_drop | perception_confidence_drop | 随机目标置信度 |
| planning_collision_risk | planning_collision_risk | 随机持续帧数的碰撞轨迹 |
| control_delay | control_delay | 0.7-1.0 秒随机制动延迟 |
| boundary_confidence_normal | normal | 置信度波动低于 drop 阈值 |
| boundary_planning_normal | normal | 规划 clearance 略高于碰撞 margin |
| composite_miss_control | perception_miss | 漏检先出现，控制延迟后出现 |
| composite_confidence_control | perception_confidence_drop | 置信度下降先出现，控制延迟后出现 |

## Parent Split

使用 parent-group exclusive 60/20/20 划分，相关变体不会跨 split：

| Split | 父场景 | 样本数 |
| --- | ---: | ---: |
| train | 3 | 30 |
| val | 1 | 10 |
| test | 1 | 10 |

方法本身不训练；split 的作用是防止同源场景出现在不同实验集合，并提供严格隔离的 test 输出。
当前 test 只有一个父场景，因此只能作为 held-out smoke test，不能给出统计置信区间。

## 复现

```bash
conda run -n yolo python scripts/generate_carla_fault_benchmark.py \
  --version v0_2 \
  --base-log-dir /data5/lzx_data/Zhijia-Guardian/datasets/carla/base_v0_1 \
  --output-root /data5/lzx_data/Zhijia-Guardian/datasets/carla/fault_benchmark_v0_2 \
  --seed 42 \
  --clean
```

生成文件：

```text
fault_benchmark_v0_2/
  raw/logs/*.json
  raw/labels/*.label.json
  raw/labels/manifest.json
  canonical/scenarios.jsonl
  canonical/splits/train.jsonl
  canonical/splits/val.jsonl
  canonical/splits/test.jsonl
```

## 结果

正式运行 commit：`7b3cafd`。

### 全量 50 场景

| 方法 | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0143 |
| Rule-only | 0.8000 | 0.8056 | 0.8000 | 1.0000 | 0.0200 |

### Parent-isolated test 10 场景

| 方法 | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0143 |
| Rule-only | 0.8000 | 0.8056 | 0.8000 | 1.0000 | 0.0200 |

Rule-only 的 10 个全量错误均发生在 composite variant：5 个 perception miss 和 5 个
confidence drop 被下游高权重 `control_delay` 覆盖。Multi-Agent 按模块分诊断，并在上游证据
早于下游至少 0.25 秒时提升上游候选，因此恢复正确根因。两个 boundary-normal variant 均未误报。

结果目录：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/carla_fault_v0_2_seed42/
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/carla_fault_v0_2_test_seed42/
```

## 局限与下一步

- 20 个百分点提升来自明确设计的时序复合故障，证明的是模块协作与时序排序机制有效，不代表
  对任意自然事故都有同等提升。
- 5 个父场景共享同一种“跟随静止前车”模板，环境多样性仍不足。
- 除单例 control-delay RGB demo 外，v0.2 主要是离线信号级注入，未全部重跑车辆动力学。
- 下一步应扩展不同道路/天气/参与者与多 seed，并批量执行闭环 control/planning fault。
