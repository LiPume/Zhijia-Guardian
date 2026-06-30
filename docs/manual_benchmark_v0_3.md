# Manual Canonical Benchmark v0.3

## 目标

manual v0.2 在控制风险时间改为“首次 TTC 跌破 1.5 秒”后，暴露出 6 条复合样本的
oracle 时序与可观测证据不一致。v0.3 不修改诊断权重来掩盖问题，而是重建数据生成流程：

1. 先生成 ego 和 actor 的完整物理时序。
2. 从时序计算首次 TTC 阈值穿越时间。
3. 感知/规划根因注入在风险出现前 0.5-1.0 秒。
4. 控制延迟从风险首次出现时开始计时。
5. normal 在风险出现时及时制动；复合样本在上游异常后再注入下游控制延迟。

旧 v0.1/v0.2 数据和结果继续保留用于历史复现，v0.3 是当前正式 manual benchmark。

## 数据设计

- 72 条场景，6 类标签各 12 条，seed 42。
- 12 条 `composite`，其中 7 条包含可评价的“上游根因 + 下游控制延迟”。
- 三种数据形态：`perception_like_nuscenes`、`planning_like_nuplan`、
  `full_stack_like_carla`。
- scenario ID 和文件名不含标签；oracle 只由 evaluator 读取。
- `source.generation` 不进入 `observed_view()`。
- 规划轨迹在 oracle 时间前保持安全，仅在规划故障开始后穿过目标预测位置。
- confidence、目标状态和控制命令带随机扰动，但根因 evidence 的首次时间必须等于 oracle 时间。

数据目录：

```text
/data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3/
```

## 正式结果

数据和评估 commit：`0c7e220`。

| 方法 | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| Single-LLM / DeepSeek V4 Pro | 0.9861 | 0.9861 | 0.9861 | 0.8167 | 0.3333 | 0.6250 | 0.1271 |
| Rule-only | 0.9028 | 0.9066 | 0.9028 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |

Rule-only 的 7 条错误全部发生在复合故障：它把 2 条 perception miss、1 条 confidence drop
和 4 条 planning risk 判成下游 control delay。Multi-Agent 先由模块 Agent 独立诊断，再根据
上游 evidence 至少早 0.5 秒的时间关系恢复根因。

Single-LLM 只有 1 条分类错误，但 Evidence Correctness 只有 0.6250，Hallucination Rate 为
0.1271，未达到项目小于等于 0.10 的目标。它经常给出正确标签，却为 claim 引用语义上不支持
该标签的 TTC、碰撞或距离 evidence。因此产品默认仍使用确定性的 Multi-Agent + Tools，LLM
只适合做受约束的可选报告生成器。

正式比较包：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/manual_v0_3_seed42/
```

## 复现

```bash
conda run -n yolo python scripts/generate_manual_scenarios.py \
  --version v0_3 \
  --count 72 \
  --seed 42 \
  --output /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --clean

conda run -n yolo python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_multi_agent_seed42 \
  --seed 42
```

Single-LLM 运行需要显式传入 `--enable-llm`，并从被 Git 忽略的 `.env` 读取 API 配置。

## 结论边界

- 满分只说明预定义工具和时序因果规则能处理这个可控 synthetic benchmark，不代表自然事故泛化。
- 样本与阈值工具仍来自同一工程定义，下一步需要多 seed、held-out 模板和 SafeBench/CARLA
  更多场景验证。
- manual benchmark 的角色是单元级和机制级对比，不替代真实传感器感知或量产 ADS 评估。
