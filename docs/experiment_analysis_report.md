# 智驾卫士实验分析报告

版本：2026-07-01  
实验表工具：`0cbe5bd`，时序消融实现：`e6fe4b8`  
数据与输出根目录：`/data5/lzx_data/Zhijia-Guardian`

## 1. 摘要

现有实验已经足够形成项目申报、阶段验收或创新项目使用的实验分析报告，也足够整理成主结果表、
消融表、真实数据表和效率表。当前证据支持以下结论：

1. 在带已知根因的 manual/CARLA 受控故障中，完整 Multi-Agent + Tools 能利用模块异常的时间先后，
   区分上游感知/规划根因与下游控制响应异常。
2. 五个 manual seed、共 360 条场景中，完整方法 Macro-F1 为 `1.0000±0.0000`；关闭时序因果排序后为
   `0.8707±0.0215`，与 Rule-only 完全一致。收益来自跨模块时序归因，而不是简单增加 Agent 数量。
3. 在 CARLA 真实闭环动力学和 held-out 夜间风暴中，完整方法均恢复了上游根因；无时序消融会把
   规划/感知故障误判为下游 `control_delay`。
4. Single-LLM/DeepSeek 在 manual seed 42 上分类准确，但 Evidence Correctness 仅 `0.6250`、
   Hallucination Rate 为 `0.1271`，不适合作为默认可信报告生成路径。
5. nuScenes 真实图像实验证明了“真实相机帧 -> detector -> Canonical Schema -> Agent 报告”链路可运行，
   但没有 fault/root oracle，因此只能报告 detector 指标和诊断假设。

当前实验不能支持以下结论：

- 不能声称自然道路事故根因准确率为 100%。
- 不能声称极端天气下真实视觉 detector 鲁棒；天气实验的 detections 为 annotation-derived。
- 不能把 nuScenes 的 5 个 `perception_miss` 假设写成“5/5 诊断正确”。
- Qwen3.7-Plus 目前只完成 prepare-only 输入校验，尚未配置 DashScope Key，不纳入结果表。

## 2. 研究问题

- **RQ1 诊断准确性：** 能否识别故障类型、根模块和故障开始时间？
- **RQ2 协作机制贡献：** 提升来自多 Agent 数量，还是跨模块时序因果排序？
- **RQ3 报告可信度：** 结论是否引用有效证据，是否出现无依据输出？
- **RQ4 真实数据兼容性：** 真实 nuPlan/nuScenes/CARLA 数据能否进入统一 Schema 和诊断流程？
- **RQ5 工程开销：** 确定性诊断能否以毫秒级延迟离线批处理？

## 3. 数据集与边界

| 数据集 | 规模 | 数据性质 | 可评估内容 | 不能评估内容 |
| --- | ---: | --- | --- | --- |
| Manual v0.3 multi-seed | 5×72=360 | Canonical 时序合成，六类均衡，含噪声/边界/复合故障 | Fault/Root/Time/报告质量 | 自然道路泛化 |
| nuPlan perturbation v0.1 | 5 个真实父场景、10 条成对轨迹 | 真实场景骨架 + 安全/危险规划扰动 | 规划风险诊断、adapter 兼容 | 原生 planner/控制故障 |
| CARLA v0.2-riskfix | 5 个父日志、50 条；test 10 条 | 离线随机信号注入、边界与复合故障 | held-out parent 诊断 | 完整闭环动力学 |
| CARLA closed-loop v0.1 | 5 个出生点、15 条 | normal/control/planning 实际重跑 | 碰撞结果、时序根因 | 大规模自然交通分布 |
| CARLA extreme weather v0.1 | 3 种天气×4 类=12；test 4 条 | 重雨/浓雾/夜间风暴仿真环境 | 天气上下文下诊断机制 | 真实视觉天气鲁棒性 |
| nuScenes real YOLO v0.1 | 5 个 scene、202 帧 | 真实 CAM_FRONT + YOLOv8n | detector 召回/精度、无标签诊断 | Fault/Root Accuracy |

所有带故障指标的数据均保持 observed/oracle 分离：Agent、Rule-only 和 LLM 只能读取
`ScenarioRecord.observed_view()`；`oracle` 只由 `run_eval.py` 读取。nuPlan `scenario_tag` 只作为上下文，
不作为故障标签。场景 ID 和路径不包含 fault/root 名称。

## 4. 对比方法

### 4.1 Rule-only

将全部工具 evidence 放入同一个加权规则表，按固定优先级选择标签。它没有模块 fan-out/fan-in，也不
判断上游异常是否早于下游异常。

### 4.2 Multi-Agent w/o Temporal Causal Ranking

保留 Scene、Metric、Perception、Planning、Control、Root Cause 节点，保留相同工具、evidence、模块
输出和 trace，只关闭 Root Cause Agent 的时序因果加分。这是本报告新增的严格消融。

### 4.3 Multi-Agent + Tools

完整方法。Perception/Planning/Control Agent 形成模块候选，Root Cause Agent 根据异常开始时间和模块
顺序执行 fan-in：若上游感知/规划异常至少早于下游异常 0.25 秒，则提升上游候选分数。

### 4.4 Single-LLM/DeepSeek V4 Pro

模型一次读取去标签化场景摘要和 metrics 摘要，直接输出结构化诊断。输入删除 `supports`、
`contradicts` 和故障提示文本；模型必须引用已有 evidence ID。该方法只在 seed 42 调用真实 API。

### 4.5 Qwen Visual Review（未进入结果表）

`direct_vlm` 只看 8 张原始相机帧；`vlm_with_tools` 再加入去标签化 evidence。当前 5 个 nuScenes
片段已完成抽帧和 SHA-256 校验，但没有 DashScope Key，不能填写结果。

## 5. 指标定义

| 指标 | 定义 |
| --- | --- |
| Fault Accuracy | 故障类型预测正确场景数 / 总场景数 |
| Fault Macro-F1 | 各故障类别 F1 的非加权平均 |
| Root Top-1 | 根模块 Top-1 正确场景数 / 总场景数 |
| Time Coverage | 有故障 oracle 的场景中输出故障时间的比例 |
| Time MAE@Correct | 仅在故障类别预测正确时计算开始时间绝对误差均值 |
| Evidence Coverage | 有有效 evidence ID 的 claim 数 / claim 总数 |
| Evidence Correctness | 被引用 evidence 支持且不反驳 claim 标签的比例 |
| Hallucination Rate | 无证据、证据不存在或证据反驳结论的 claim 比例 |

`normal` evidence 同时记录 `supports=[normal]` 和对故障标签的 `contradicts`，因此正常报告也能计算。
Time MAE 必须与 Time Coverage 同时阅读，防止通过不输出困难时间降低误差。

## 6. 具体实验流程

### 6.1 环境与版本

```bash
cd /home/lzx/Zhijia-Guardian
conda activate yolo
pip install -e ".[dev,llm]"
git rev-parse HEAD
pytest
```

每个 run 写入 `run_meta.json`，记录 run_id、method、dataset、seed、配置和 git commit。

### 6.2 Manual v0.3 五 seed 生成

使用 seed `7/42/2026/3407/9012`，每个 seed 72 条、六类各 12 条：

```bash
for seed in 7 42 2026 3407 9012; do
  python scripts/generate_manual_scenarios.py \
    --version v0_3 --count 72 --seed ${seed} \
    --output /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3_multiseed/seed_${seed} \
    --clean
done
```

每条样本先生成 ego/actor 时序，再以 TTC 首次低于阈值的时间定义风险开始。感知/规划根因必须早于
下游控制异常；同时加入位置、置信度、控制抖动、边界 TTC 和复合故障。

### 6.3 三种确定性方法

以 seed 42 为例：

```bash
python experiments/run_eval.py \
  --method rule_only \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3_multiseed/seed_42 \
  --run-id manual_v0_3_seed42_rule

python experiments/run_eval.py \
  --method multi_agent_no_temporal_causal \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3_multiseed/seed_42 \
  --run-id manual_v0_3_seed42_no_temporal

python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3_multiseed/seed_42 \
  --run-id manual_v0_3_seed42_full
```

每条场景执行：

```text
adapter -> observed_view -> metric tools
        -> Perception / Planning / Control Agents
        -> Root Cause fan-in -> diagnosis_v1 -> report_v1
        -> evaluator 单独读取 oracle -> eval.csv / summary.json
```

### 6.4 Single-LLM

```bash
python experiments/run_eval.py \
  --method single_llm --enable-llm \
  --llm-config configs/llm_deepseek.yaml \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_single_llm_deepseek_v4_pro_seed42
```

API 输入只包含 observed 场景统计和去标签化 metrics；API Key、Base URL 不写入输出包。

### 6.5 CARLA v0.2-riskfix

历史 v0.2 使用“最低 TTC 时刻”作为 control-delay 注入起点，一条场景的 oracle 与首次风险响应矛盾。
该历史数据不进入最终表。修正版从 TTC 首次低于 1.5 秒开始延迟控制：

```bash
python scripts/generate_carla_fault_benchmark.py \
  --version v0_2 --seed 42 --clean \
  --base-log-dir /data5/lzx_data/Zhijia-Guardian/datasets/carla/base_v0_1 \
  --output-root /data5/lzx_data/Zhijia-Guardian/datasets/carla/fault_benchmark_v0_2_riskfix
```

五个 parent 按 60/20/20 分组，同一 parent 的 variant 只进入同一 split。最终表使用 test 的 10 条样本。

### 6.6 CARLA 闭环与天气

闭环数据实际重新运行 normal、control-delay 和 planning-fault，而非只改 JSON。5 条 normal 无碰撞，
10 条故障均发生碰撞。天气实验将 `heavy_rain_day/dense_fog_dawn/night_storm` 分给 train/val/test，
最终天气表只使用 4 条 held-out night-storm 场景。

### 6.7 nuScenes 真实视觉

```bash
python scripts/run_nuscenes_yolo_benchmark.py --clean

python experiments/run_diagnosis.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1/canonical/scenarios.jsonl \
  --run-id nuscenes_real_yolo_v0_1_multi_agent \
  --method multi_agent_tools
```

YOLO 框与投影到 CAM_FRONT 的 nuScenes 3D annotation 做 IoU 关联。annotation 只用于 detector 评估和
世界坐标回填，不作为故障 oracle。该入口不生成 Accuracy、F1 或 failure package。

### 6.8 延迟与表格导出

```bash
python scripts/benchmark_diagnosis_latency.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3_multiseed/seed_42 \
  --repeats 10 \
  --output /data5/lzx_data/Zhijia-Guardian/outputs/benchmarks/diagnosis_latency_manual_v0_3.json

python experiments/export_experiment_tables.py
```

延迟范围为“Canonical Scenario 到 diagnosis”，包含 metrics，不包含磁盘读取、绘图、写报告和云端 API。
每种方法测量 72×10=720 次。

## 7. 主结果

### 7.1 Manual v0.3 seed 42

| 方法 | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct | Evidence Correctness | Hallucination |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule-only | 0.9028 | 0.9066 | 0.9028 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| Multi-Agent w/o temporal | 0.9028 | 0.9066 | 0.9028 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| Multi-Agent + Tools | **1.0000** | **1.0000** | **1.0000** | 1.0000 | 0.0000 | **1.0000** | **0.0000** |
| Single-LLM/DeepSeek V4 Pro | 0.9861 | 0.9861 | 0.9861 | 0.8167 | 0.3333 | 0.6250 | 0.1271 |

DeepSeek 分类接近完整方法，但时间覆盖较低且报告证据正确性明显下降，说明只看分类准确率会高估
产品可信度。

### 7.2 五 seed 稳定性

| 方法 | Accuracy mean±std | Macro-F1 mean±std | Root Top-1 mean±std | Time MAE@Correct mean±std |
| --- | ---: | ---: | ---: | ---: |
| Rule-only | 0.8639±0.0228 | 0.8707±0.0215 | 0.8639±0.0228 | 0.0000±0.0000 |
| Multi-Agent w/o temporal | 0.8639±0.0228 | 0.8707±0.0215 | 0.8639±0.0228 | 0.0000±0.0000 |
| Multi-Agent + Tools | **1.0000±0.0000** | **1.0000±0.0000** | **1.0000±0.0000** | 0.0017±0.0037 |

完整方法在 360 条场景中恢复了无时序消融错误的 49 条复合故障。无时序消融与 Rule-only 完全相同，
说明仅把规则拆成多个 Agent 不会自动提升效果；真正有效的是 fan-in 阶段的时间因果约束。

### 7.3 跨数据集消融

| 数据集/划分 | N | Rule Macro-F1 | No-temporal Macro-F1 | Full Macro-F1 | Full Root Top-1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| CARLA v0.2-riskfix held-out test | 10 | 0.8056 | 0.8056 | **1.0000** | 1.0000 |
| CARLA closed-loop all parents | 15 | 0.5556 | 0.5556 | **1.0000** | 1.0000 |
| CARLA night-storm held-out | 4 | 0.3750 | 0.3750 | **1.0000** | 1.0000 |
| nuPlan paired perturbation | 10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

nuPlan 只有单一规划异常/正常配对，没有跨模块传播，三种方法均饱和，适合作为 adapter/Planning Agent
集成测试，不适合证明多 Agent 优势。CARLA 闭环和天气包含“上游异常 + 下游控制表现”，能区分时序
排序能力，但样本量仍小。

## 8. 真实数据观察

| 指标 | nuScenes real YOLO v0.1 |
| --- | ---: |
| 真实 scene / 帧数 | 5 / 202 |
| Annotation Recall | 0.4706 |
| 50 米内关键目标 Recall | 0.5391 |
| Detection Precision | 0.7248 |
| 匹配目标类别准确率 | 0.9290 |
| Fault/root oracle | 无 |

五个片段均输出 `perception_miss` 主导的工程假设，Planning/Control Agent 因输入缺失而跳过。轻量 COCO
detector 对已匹配目标分类较准，但对远距离、小目标、遮挡和拥挤目标召回不足。“5/5 perception_miss”
是输出分布，不是准确率。

## 9. 运行效率

| 方法 | Median ms/场景 | P95 ms/场景 | 吞吐量 场景/s |
| --- | ---: | ---: | ---: |
| Rule-only | 6.47 | 9.83 | 186.4 |
| Multi-Agent w/o temporal | 7.41 | 10.75 | 162.3 |
| Multi-Agent + Tools | 7.05 | 10.67 | 170.9 |

完整多 Agent 的 P95 约 10.7 ms，适合离线批量预诊断。方法间差异小于 1 ms 量级，不应过度解读
吞吐量顺序；媒体解码、模型推理和展示才会占主要时间。

## 10. 错误与案例分析

### 10.1 Rule-only / 无时序消融

主要错误是把下游 `control_delay` 当主因。例如规划轨迹先进入障碍物，随后控制没有及时制动；单层
权重中 brake-delay 高于 planning risk。完整方法检测到规划 evidence 至少早 0.25 秒，将 planning
提升为主因，同时保留 control 为次因。

### 10.2 Single-LLM

主要问题不是分类，而是证据引用：部分 claim 引用了不支持对应标签的 evidence，或没有时间 evidence
仍给出故障时间。因此产品默认关闭 LLM，结构化规则报告作为主输出。

### 10.3 真实图像

第一次运行时，置信度自然波动使所有片段被误判为 confidence-drop。修订后要求低置信度持续两帧、
目标仍是关键目标且框面积可比，并在持续漏检与置信度变化并存时优先报告漏检。修订后 Manual、
CARLA closed-loop 和 weather 回归未下降。

### 10.4 CARLA 历史数据修正

旧 `fault_benchmark_v0_2` 的 control-delay 注入从最低 TTC 时刻开始，而工具使用首次 TTC 阈值穿越，
产生“oracle 说延迟，但首次风险后 0.3 秒已制动”的矛盾样本。最终结果只使用重新生成的
`fault_benchmark_v0_2_riskfix`；旧数字保留用于审计，不进入主表。

## 11. 有效性威胁

1. **受控数据偏差：** Manual 和 CARLA 注入与诊断工具共享故障定义，满分表示机制闭环，不等于未知
   自然事故泛化。
2. **样本规模：** CARLA held-out test 10 条，天气 test 4 条，需扩展地图、出生点和 seed。
3. **真实标签缺失：** nuScenes 没有被测 planner/control 和 root oracle，只能评价 perception 兼容性。
4. **LLM 对比范围：** DeepSeek 只运行一个 seed；Qwen 尚未调用，不能比较云端平均延迟和成本。
5. **天气感知边界：** CARLA weather detections 来自 annotation，不是图像 detector 输出。
6. **人工评价缺失：** 尚未由多名工程背景评审者对报告清晰度和可操作性做盲评。

## 12. 推荐表述

推荐：

> 在五个随机种子的 360 条受控场景中，完整 Multi-Agent + Tools 的 Fault Macro-F1 和 Root Top-1
> 均为 1.0000；关闭跨模块时序因果排序后，Macro-F1 降至 0.8707±0.0215。CARLA 真实闭环与 held-out
> 夜间风暴复现了同一趋势，说明时序 fan-in 能减少将上游感知/规划故障误判为下游控制异常。真实
> nuScenes 图像链路进一步验证了产品对实际相机数据与 detector 输出的兼容性，但因缺少系统故障
> oracle，本文不报告真实道路根因准确率。

不推荐：

> 系统在真实自动驾驶场景中的事故根因诊断准确率达到 100%。

## 13. 后续实验优先级

1. 为 20-50 个真实/仿真视觉片段建立人工复核表，比较 Direct-Qwen、Qwen+Tools 和 YOLO+Tools。
2. 将 CARLA weather 接真实 RGB detector，测 clear/rain/fog/night 的 recall degradation 和诊断变化。
3. 将 closed-loop 扩展到至少 20 个 parent、3 个地图和 3 个 seed，只报告 parent-held-out 结果。
4. 增加 Root Top-3、报告人工 usefulness、单场景 token 成本和云端 P50/P95 延迟。

## 14. 结果文件

- 主表：[main_results.csv](tables/main_results.csv)
- 五 seed 明细：[manual_multiseed.csv](tables/manual_multiseed.csv)
- 五 seed 汇总：[manual_multiseed_aggregate.csv](tables/manual_multiseed_aggregate.csv)
- 真实数据：[real_data_results.csv](tables/real_data_results.csv)
- 延迟：[diagnosis_latency.csv](tables/diagnosis_latency.csv)
- 原始输出：`/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/`

重新导出 CSV：

```bash
python experiments/export_experiment_tables.py
```
