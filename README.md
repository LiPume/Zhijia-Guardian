# 智驾卫士（Zhijia-Guardian）

> **面向 openpilot-like ADS 消息流与控制链路的工具增强型多 Agent 主动因果诊断工作流。**

智驾卫士不是“通用事故根因判定器”。它面向 openpilot-like 离线消息时间线：确定性工具先计算事实；Agent 再形成可证伪假设、选择下一项检查或合成干预、比较预测与结果；Evidence Auditor 最终限制无证据结论。

## 解决的问题与边界

研究对象包括 rlog/qlog 或兼容输入中的 `can`、`sendcan`、`carState`、`carControl`、`controlsState`、`selfdriveState`、规划相关消息、`pandaStates`、`onroadEvents`，以及消息频率、缺失、延迟、依赖和控制指令传递关系。

系统可定位异常消息链路或控制链路的 `suspected_link`；缺少可观测证据时会输出 `insufficient_observability`、`insufficient_evidence` 或 `cannot_determine_root_cause`。只有在受控 synthetic ADSLogRecord 回放中，干预结果符合预期时，系统才允许输出 `validated_root_cause`；它仅代表该注入机制在该合成样例中得到验证，绝不等同于真实车辆事故根因。

本项目不覆盖所有自动驾驶系统、不替代工程师、不从公开日志恢复真实事故根因，也不宣称多 Agent 必然优于线性流程。

特别说明：**nuScenes、nuPlan、commaCarSegments 不能组成同一条真实端到端路线。**

## 为什么采用工具使用型多 Agent

LLM（可选）不直接读日志猜根因。工具负责计算消息间隔、CAN 地址、控制链路一致性和安全事件；Agent 维护 hypothesis board、选择注册工具与停止条件；Auditor 审核 evidence ID、数据来源边界和根因语言；Report Agent 只能渲染已有结构化状态。

默认 `LLM_PROVIDER=none`，因此 CI 和 demo 不需要 API key。`LLM_PROVIDER=openai` 或 `LLM_PROVIDER=deepseek` 可进行一次 OpenAI-compatible 的结构化 `select_specialists` 工具调用；缺少密钥、网络失败或返回非法动作时，系统会自动退化为离线确定性模式。

```text
rlog/qlog ── OpenpilotLogAdapter ── DiagnosticCase（隐藏 oracle）
                                      │
开始 → Case Manager → 条件分派专业 Agent → Hypothesis Agent
                    ├ 消息流工具
                    ├ CAN 工具
                    ├ 控制链路工具
                    └ 安全/车辆接口工具
                                      │
Counterfactual Agent → Validation Agent → Evidence Auditor → Report Agent
```

## Agent 与工具

| Agent | 诊断目标 | 注册的确定性工具 |
| --- | --- | --- |
| Case Manager | 盘点数据并路由 | topic 目录、依赖图 |
| Message Flow | 频率、间隔、陈旧与时间顺序 | topic 频率、gap、时间戳连续性、陈旧检测 |
| CAN Diagnostic | CAN/sendcan 覆盖与时序 | 帧提取、地址汇总/频率、CAN gap |
| Control Link | 指令传递 | 控制响应、carControl→sendcan、sendcan→carState、首次分歧 |
| Safety / Vehicle Interface | 安全阻断与事件 | panda 状态、onroad 事件提取 |
| Hypothesis / Counterfactual / Validation | 主动因果诊断 | 假设构建、合成 repair/replay、预测验证 |
| Evidence Auditor | 证据约束结论 | evidence 引用、来源边界与根因语言检查 |
| Report Agent | 事实性表达 | diagnosis/report/package 写入 |

工作流具有显式状态、条件路由、Agent 私有状态、结构化输出、调用轨迹与上限：`max_agent_rounds=3`、`max_tool_calls=30`。

## 跨数据源证据边界

| 角色 | 数据源 | 允许用途 |
| --- | --- | --- |
| 主诊断 | openpilot-like / commaCarSegments | 对单个 route/segment 提供消息、CAN 与控制链路证据 |
| 辅助感知证据 | nuScenes | 归一化感知 evidence adapter；绝不声称与主路线相同 |
| 辅助规划证据 | nuPlan | 归一化规划 evidence adapter；绝不声称与主路线相同 |
| 因果验证 | synthetic ADSLogRecord；CARLA 后续接入 | 受控故障注入、repair/replay 和仅评估端可见的 oracle |

当前可运行验证沙箱是 synthetic ADSLogRecord；CARLA 是下一后端，不是已完成能力。`decision_board.json` 会记录竞争假设、可行动作、预期信息增益/成本和最终选择。

## 快速开始

```bash
cd /home/lzx/Zhijia-Guardian
conda env create -f environment.yml  # 或复用已有 Zhijia 环境
conda run -n Zhijia pip install -e '.[dev,openpilot]'
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
conda run -n Zhijia python scripts/run_agentic_demo.py --config configs/demo.yaml
```

可复现 demo 会生成干净的 openpilot-like 时间线、删除一段 `sendcan` 消息、向所有 Agent 隐藏扰动 oracle，并写入：

```text
$ZHIJIA_DATA_ROOT/outputs/synthetic-openpilot-perturbed/
├── diagnosis.json
├── evidence.jsonl
├── agent_trace.json
├── hypotheses.json
├── interventions.json
├── decision_board.json
├── report.md
└── failure_sample_package/manifest.json
```

预期结果：合成 `sendcan` gap 会形成可检验的 `carControl -> sendcan` 假设；repair replay 消除该 gap 后，系统只针对该注入合成机制输出 `validated_root_cause`。

## 真实 openpilot 日志与数据策略

上游参考实现存放在外部目录，永不提交：

```bash
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
bash scripts/setup_openpilot_reference.sh
export OPENPILOT_ROOT=$ZHIJIA_DATA_ROOT/reference/openpilot
conda run -n Zhijia python scripts/inspect_openpilot_log.py /path/to/one.rlog.zst --openpilot-root "$OPENPILOT_ROOT"
```

`OpenpilotLogAdapter` 使用上游 `openpilot.tools.lib.logreader.LogReader`；本项目不会复制或修改 openpilot 源码。只获取明确指定的单个 rlog/qlog segment（非必要不下载相机视频），放入 `$ZHIJIA_DATA_ROOT/raw/openpilot/`，并始终排除在 Git 之外。`scripts/fetch_minimal_sample.py` 记录官方最小 qlog smoke 数据源。

## 当前状态与限制

- 已完成：离线工具工作流、主动假设/干预/验证闭环、synthetic 扰动、Pydantic 契约、证据审计、报告与 failure package、真实日志 adapter、CARLA-compatible ADSLogRecord adapter。
- 已验证：官方单 qlog 可解析；由于 qlog 抽样与 topic 缺失，真实日志缺少控制/CAN 信号时会报告可观测性不足，而不会补造事实。
- 未完成：CARLA runtime 与真实闭环 recorder；系统性 benchmark；真实自然事故根因验证。

详见 [Agent 逻辑架构](docs/agent_logic_architecture.md)、[设计说明](docs/design.md)、[主动因果工作流](docs/active_causal_workflow.md)、[数据来源](docs/data_sources.md)、[限制](docs/limitations.md) 和 [旧版重校准说明](docs/legacy_recalibration.md)。
