# Agent 逻辑架构

本文描述当前可执行的工作流，而不是把每一个 Python 节点都称为 Agent。系统目标是对 openpilot-like 消息链路做**受证据约束的离线调查**：工具计算事实，调查 Agent 选择必要检查、维护竞争假设并决定何时停止。

## 1. 设计硬约束

1. **工具计算事实。** 频率、gap、时间戳、CAN 地址、控制一致性与 safety event 只能由确定性工具生成。
2. **oracle 不可见。** `DiagnosticCase.observed_copy()` 在进入 workflow 前移除 oracle；synthetic 注入标签只供 evaluator 使用。
3. **主路线与辅助证据分离。** 原生依赖图只容纳 `modelV2`、`longitudinalPlan`、`carControl`、`sendcan`、`carState` 等主路线 topic。`zgAux.perceptionEvidence`、nuScenes、nuPlan 进入 `AuxiliaryEvidenceBundle`，固定不是同一路线。
4. **结论按可观测性分级。** 真实日志最多得到 `suspected_link`、`insufficient_evidence` 或 `cannot_determine_root_cause`。synthetic 对照成功时只输出 `counterfactually_supported_injected_fault_location`，不输出真实世界根因。
5. **不以角色数量证明 Agentic。** 只有存在局部目标、受限工具、条件分支和停止条件的调查角色才是 Agent；执行、审计和渲染是受调用的基础设施。

## 2. 执行图

```text
DiagnosticCase（oracle 已移除）
          │
          ▼
   Case Manager Agent
          │  初始只派发 Message Flow
          ▼
Message Flow Investigator ── message-gap evidence ──┐
          │                                         │
          │  按证据触发，而非固定 fan-out             │
          ├──── CAN Investigator（can/sendcan gap）  │
          ├──── Control Investigator（plan/control/sendcan gap）
          └──── Safety Investigator（sendcan gap）   │
                                                    ▼
                                  Hypothesis Investigation Agent
                                     │ 竞争假设 + priority score
                                     ▼
                           Counterfactual Executor（synthetic only）
                           targeted / sham / alternative replay
                                     ▼
                               Validation Tool（比较预注册预测）
                                     ▼
                         Evidence Auditor → Report Renderer
```

默认上限为 `max_agent_rounds=3`、`max_tool_calls=30`。达到预算后也会运行 Auditor 与 Renderer，输出明确的停止原因。

## 3. 调查 Agent

| Agent | 诊断目标 | 可调用工具 / 局部决策 | 停止条件 |
| --- | --- | --- | --- |
| Case Manager | 清点可观测 topic，控制预算 | `list_available_topics`、`build_message_dependency_graph`；只把候选 specialist 交给后续 evidence 路由 | 初始消息流检查已安排 |
| Message Flow Investigator | 找到频率、gap、时间倒退、stale 事实 | 对实际存在的 `modelV2`、`longitudinalPlan`、`carControl`、`sendcan` 选择消息工具 | 已检查可观测主 topic |
| CAN Investigator | 检查 CAN 通信健康 | 地址覆盖、频率、gap；只在 `can/sendcan` gap 可区分假设时调用 | 无 CAN topic 或检查完成 |
| Control Investigator | 定位控制传递首次分歧 | command-response、`carControl/sendcan`、`sendcan/carState` 一致性 | 缺关键 topic 或检查完成 |
| Safety Investigator | 检查安全层/车端接口阻断 | `pandaStates`、`onroadEvents` 提取；只在下游发送 gap 有意义时调用 | 无 safety topic 或检查完成 |
| Hypothesis Investigation Agent | 生成竞争解释、选择下一动作 | `formulate_hypotheses`、`rank_action_candidates`、`choose_highest_priority` | 没有可证伪假设、没有可行动作或预算耗尽 |

可选 DeepSeek/OpenAI 路由只看到 topic 名和候选 specialist 名称；它不读取 payload、oracle 或 finding，失败时退化为相同的离线规则。

## 4. 竞争假设而非固定故障表

对每个主路线直接 gap，系统生成一个 `propagation` 假设，例如：

```text
modelV2 gap          → modelV2 -> longitudinalPlan
longitudinalPlan gap → longitudinalPlan -> carControl
sendcan gap          → carControl -> sendcan
```

当同一窗口出现两个及以上直接 gap 时，额外生成：

```text
independent_fault: 两个 gap 是独立故障
common_cause:       一个未观测共同原因影响两个 topic
```

每个假设都记录 supporting evidence、预测、下一动作、失败条件与理由。没有足够日志能区分竞争解释时，动作是请求额外可观测性，而不是猜测上游根因。

## 5. 可解释动作选择

当前没有使用未经校准的“expected information gain”。每个 `ActionCandidate` 输出：

```text
diagnostic_priority_score =
  evidence_strength
  × downstream_explanatory_coverage
  × discriminability
  × feasibility
  / execution_cost
```

- `evidence_strength`：从 `gap_s / median_s` 归一化得到；
- `downstream_explanatory_coverage`：依赖图中的可达下游节点比例；
- `discriminability`：该 repair 能区分的竞争解释数量；
- `feasibility`：是否为 synthetic、是否有注册 repair；
- `execution_cost`：当前 replay/工具成本。

分数及各组成项都写入 `decision_board.json`。未来只有在 synthetic fault matrix 提供了经过校准的 `P(outcome | hypothesis, action)` 后，才会切换到条件熵信息增益。

## 6. 对照验证与结论边界

`CounterfactualExecutor` 不是可自由推理的 Agent。它仅在 synthetic case 且存在 clean reference 时按 Investigation Agent 的选择执行三种回放：

1. `targeted_repair`：恢复假设指向的 topic；
2. `sham_repair`：恢复不应影响目标 gap 的对照 topic；
3. `alternative_repair`：恢复竞争链路的相邻 topic。

`ValidationTool` 要求三个预注册检查同时成立：

```text
targeted_direct_gap_removed       = true
sham_preserved_target_gap         = true
alternative_preserved_target_gap  = true
```

成功后只能得到 `counterfactually_supported_injected_fault_location`。如果要声称“传播机制获得支持”，还必须有独立、预注册的下游异常恢复证据；当前 MVP 不做此强主张。

## 7. Evidence Auditor 与 Report Renderer

`EvidenceAuditor` 是基础设施而不是凑数量的 Agent。它验证每个 finding 的 evidence 引用、阻止真实 case 使用 synthetic-only 分类，并给跨数据源辅助证据附加非同一路线警告。

`ReportRenderer` 只能序列化已经审计的状态，生成：

```text
diagnosis.json
evidence.jsonl
agent_trace.json
hypotheses.json
interventions.json
decision_board.json
report.md
failure_sample_package/
```

它不会新增任何 finding 或自然语言事实。

## 8. 如何证明不是固定 DAG

`agent_trace.json` 必须随 case 改变。例如：

```text
modelV2 gap:
Case Manager → Message Flow → Hypothesis Investigation → controls → audit → render

sendcan gap:
Case Manager → Message Flow → CAN / Control / Safety → Hypothesis Investigation
→ controls → audit → render
```

测试覆盖了这两条不同 trace。仍需在后续 fault matrix 中比较固定 pipeline、规则基线、去掉竞争假设和去掉 Auditor 的消融，才能主张动态调查路由带来方法收益。
