# Multi-Agent Diagnosis Graph

## 定位

主方法是一个确定性的 evidence-grounded 多 Agent 图，不依赖 LLM，也不要求安装 LangGraph。
Agent 的协作价值来自模块隔离、结构化状态和时序根因汇总，不来自自由对话。

```text
                         +-> Perception Agent -+
Scenario -> Metric Agent +-> Planning Agent ---+-> Root Cause Agent
             |           +-> Control Agent ----+
             +-> Scene Agent ------------------+
```

- `Metric Agent` 统一计算 TTC、碰撞、感知、规划、控制和舒适性 evidence。
- `Scene Agent` 对齐 observed event 和 violation evidence 时间线。
- 三个模块 Agent 构成 fan-out，只读取本模块可诊断 evidence；字段缺失时返回 `skipped`。
- `Root Cause Agent` 构成 fan-in，根据模块分数、最早异常和上下游时间关系输出候选根因 Top-K。
- `Report Agent` 在图外将结构化 diagnosis 渲染成确定性 Markdown，不改变诊断结论。

## Oracle 隔离

`DiagnosisGraph.initialize_state()` 不把原始 `ScenarioRecord` 直接交给 Agent，而是从
`scenario.observed_view()` 重新构造一个 ScenarioRecord。图状态中的：

- `oracle` 固定为 `None`；
- `source.generation` 固定为空；
- 预计算 metrics 的 `scenario_id` 必须与场景一致。

原始记录和 oracle 仍留在图外，只由 `experiments/run_eval.py` 的 evaluator 读取。

## 图状态

`DiagnosisGraphState` 使用 Pydantic 严格校验，包含：

| 字段 | 内容 |
| --- | --- |
| `scenario` | 已去 oracle 的 observed ScenarioRecord |
| `metrics` | Metric Agent 输出 |
| `trace` | 顺序稳定的 AgentStepRecord 列表 |
| `module_diagnoses` | perception/planning/control 分模块结论 |
| `diagnosis` | Root Cause Agent 最终输出 |
| `executed_nodes` | 实际执行节点，用于检测漏跑和顺序错误 |

图结束时会校验执行顺序和 trace 必须严格为：

```text
metric_agent
scene_agent
perception_agent
planning_agent
control_agent
root_cause_agent
```

fan-out 表示三个模块诊断彼此不读取对方内部输出；当前为了结果顺序可复现而串行执行。后续如
单个 Agent 变成高延迟模型，可在不改变状态 contract 的前提下并发调度。

## 单场景检查

```bash
conda run -n yolo python scripts/inspect_diagnosis_graph.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --scenario-id manual_v0_3_000001
```

命令只输出图拓扑、模块状态、evidence ID、执行 trace 和预测，不输出 oracle。

完整评估仍使用统一入口：

```bash
conda run -n yolo python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_multi_agent_graph_v0_2_seed42 \
  --seed 42
```

## 回归结果

正式框架 commit：`838ba17`。

| 数据 | 场景数 | Accuracy | Macro-F1 | Root Top-1 | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manual v0.3 | 72 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| CARLA closed-loop v0.1 | 15 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

输出目录：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/runs/manual_v0_3_multi_agent_graph_v0_2_seed42/
/data5/lzx_data/Zhijia-Guardian/outputs/runs/carla_closed_loop_v0_1_multi_agent_graph_v0_2_seed42/
```

这些结果用于确认新框架没有改变已有诊断口径。manual 和 CARLA 场景仍是受控 benchmark，
不能把满分解释成自然事故泛化能力。

## 为什么暂不引入 LangGraph

当前图没有动态工具循环、人工中断或持久化恢复需求，Pydantic 状态 + 显式 DAG 已能提供：

- 节点边界；
- 条件跳过；
- fan-out/fan-in；
- 完整 trace；
- 稳定可复现测试。

此时引入 LangGraph 只会增加依赖，不会改善诊断指标。若后续加入人工复核节点、远程模型重试
或持久化 checkpoint，再把相同 node contract 包到 LangGraph 中。
