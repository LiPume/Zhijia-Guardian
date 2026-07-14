# Agent 逻辑架构

本文说明智驾卫士当前的多 Agent 逻辑。系统的核心不是让多个模型自由讨论“谁是根因”，而是让每个 Agent 在受限工具面内完成不同的诊断决策；所有事实必须来自确定性工具，所有结论必须经过 evidence 审计。

## 1. 设计原则

系统遵循四条硬约束：

1. **工具计算事实，Agent 管理诊断过程。** 消息频率、gap、CAN 地址、控制响应和 safety event 由 Python 工具计算，不由 Agent 凭文本推测。
2. **Agent 只能读取 observed view。** `DiagnosticCase.observed_copy()` 删除 `oracle` 后才进入 workflow；注入故障标签只供 synthetic 评估使用。
3. **跨数据源不伪造同一路线。** openpilot-like/commaCarSegments 是主诊断输入；nuScenes 与 nuPlan 仅以 `AuxiliaryEvidenceBundle` 形式提供辅助感知/规划证据，且固定 `same_route_as_primary=false`。
4. **验证结论分级。** 真实日志最多得到 `suspected_link`；`validated_root_cause` 只允许用于 synthetic ADSLogRecord 的受控 repair/replay 验证。

## 2. 总体工作流

```text
                  ┌─────────────────────────────┐
                  │ DiagnosticCase（oracle 隐藏） │
                  └──────────────┬──────────────┘
                                 ▼
                         Case Manager
                                 │ topic / 数据类型 / 路由
           ┌─────────────────────┼──────────────────────┐
           ▼                     ▼                      ▼
   Message Flow Agent      CAN Agent          Control / Safety Agent
           └─────────────────────┬──────────────────────┘
                                 ▼
                         Hypothesis Agent
                     ┌───────────┴───────────┐
                     │ 假设图 + 决策面板      │
                     │ 信息增益 / 成本排序    │
                     └───────────┬───────────┘
                                 ▼
                    Counterfactual Agent
                        │ synthetic 时可执行
                                 ▼
                       Validation Agent
                        │ 比较预测和结果
                                 ▼
                       Evidence Auditor
                                 ▼
                         Report Agent
```

默认上限为 `max_agent_rounds=3`、`max_tool_calls=30`。即使达到上限，Evidence Auditor 与 Report Agent 仍会运行，保证输出有明确停止原因和审计结果。

## 3. 共享状态与私有状态

### 3.1 `DiagnosticWorkflowState`

工作流共享状态包含：

| 字段 | 用途 |
| --- | --- |
| `case` | 已去除 oracle 的 `DiagnosticCase` |
| `available_topics` | Case Manager 发现的 topic |
| `requested_agents` / `completed_agents` | 调度计划与实际执行记录 |
| `tool_results` / `evidence` | 所有工具输出与稳定 evidence ID |
| `hypotheses` | 当前可证伪的机制假设 |
| `action_candidates` / `decision_board` | 候选动作、信息增益/成本及被选动作 |
| `interventions` / `validations` | synthetic repair/replay 与验证结果 |
| `audit_result` / `findings` | 审计后的结论 |
| `trace` / `stop_reason` | 可复现调用轨迹和终止原因 |

### 3.2 Agent 私有状态

每个 Agent 都有局部 `private_state`，不直接作为事实写入报告：

- Case Manager 保存发现的 topic 与候选专业 Agent。
- Hypothesis Agent 保存 hypothesis、action candidates 和选定动作。
- 其他专业 Agent 仅保留本次工具执行的局部上下文。

对外可审计内容始终通过 `ToolResult`、`Evidence`、`Hypothesis`、`Intervention`、`ValidationResult` 与 `AgentTraceEntry` 写入共享状态。

## 4. Agent 角色

### 4.1 Case Manager Agent

**目标：** 识别可观测数据并决定哪些专业检查有意义。

**工具：** `list_available_topics()`、`build_message_dependency_graph()`。

**路由规则：**

```text
任何 topic                    → Message Flow Agent
can 或 sendcan                → CAN Agent
carControl/sendcan/carState   → Control Link Agent
pandaStates/onroadEvents      → Safety Agent
```

Case Manager 可以由可选 LLM 进行一次受限的 `select_specialists` 工具调用，但 LLM 只看到 topic 名称和允许的 Agent 名称。缺少 API key 或调用失败时，自动使用确定性路由。

### 4.2 Message Flow Agent

**目标：** 检查发布链路是否存在频率异常、消息 gap、时间倒退或陈旧消息。

**工具：** `calculate_topic_frequency()`、`detect_message_gaps()`、`detect_timestamp_discontinuity()`、`detect_stale_messages()`。

当前主动诊断重点检查：`perceptionEvidence`、`longitudinalPlan`、`carControl`、`sendcan`。这些 topic 分别覆盖感知证据、规划输出、控制命令和底层发送链路。

### 4.3 CAN Diagnostic Agent

**目标：** 检查 `can` / `sendcan` 的帧覆盖、地址分布、地址频率和长时间 gap。

**工具：** `extract_can_frames()`、`summarize_can_addresses()`、`calculate_can_address_frequency()`、`detect_can_gaps()`。

该 Agent 报告通用帧级事实，不假设某一车型 DBC 语义。

### 4.4 Control Link Agent

**目标：** 检查规划/控制/车辆状态之间的消息传递，而不是直接判断车辆动力学根因。

**工具：** `check_control_command_response()`、`check_carcontrol_sendcan_consistency()`、`check_sendcan_vehicle_state_consistency()`、`find_first_divergence()`。

缺少任一关键 topic 时，工具返回 `insufficient_observability`，而不是补造控制效果。

### 4.5 Safety / Vehicle Interface Agent

**目标：** 检查安全层或车辆接口是否可能阻断下游链路。

**工具：** `extract_panda_safety_events()`、`extract_onroad_events()`。

重点字段包括 `controlsAllowed`、`safetyTxBlocked`、`faults`、`busOff`、`canError`、`commIssue`、`controlsMismatch` 与 `processNotRunning`。若日志中没有这些 topic，结论只能是不可观测。

### 4.6 Hypothesis Agent

**目标：** 将主路线的直接 evidence 转换为可被反驳的机制假设，而不是生成自由文本根因。

当前内置假设映射：

| 直接证据 | 假设链路 | 预测 |
| --- | --- | --- |
| `perceptionEvidence` gap | `perceptionEvidence -> longitudinalPlan` | 恢复感知证据发布后，该 gap 消失 |
| `longitudinalPlan` gap | `longitudinalPlan -> carControl` | 恢复规划输出发布后，该 gap 消失 |
| `sendcan` gap | `carControl -> sendcan` | 恢复发送消息后，该 gap 与首次分歧消失 |

每条 `Hypothesis` 都有 `evidence_ids`、置信度、预期观测、下一动作和理由。

### 4.7 Counterfactual Agent

**目标：** 选择并执行最有区分力的可行干预。

它不会直接读取注入 oracle。对于 synthetic case，它只能调用注册的 `run_counterfactual_repair()`：从干净基线恢复对应 topic 的消息，生成一个新的 repair replay。对于真实 rlog/qlog，没有可控基线，因此返回 `not_feasible`，不会篡改原始记录。

### 4.8 Validation Agent

**目标：** 将干预前的预测与 repair replay 的观察结果进行比较。

**工具：** `validate_counterfactual()`。

验证结果可为：

- `confirmed`：目标 gap 被修复，提升对应 hypothesis 的置信度；
- `refuted`：修复后异常仍存在，降低该 hypothesis；
- `insufficient_evidence`：没有可执行的回放或基线。

### 4.9 Evidence Auditor Agent

**目标：** 限制结论范围。

Auditor 执行：

1. 验证每个 finding 的 `evidence_id` 是否存在；
2. 检查真实 case 是否错误使用 `validated_root_cause`；
3. 对 nuScenes/nuPlan 辅助 evidence 写入“非同一路线”边界警告；
4. 将未验证根因降级为 `suspected_link`、`insufficient_evidence` 或 `cannot_determine_root_cause`；
5. 只允许 synthetic 且 validation 为 `confirmed` 的机制输出 `validated_root_cause`。

### 4.10 Report Agent

**目标：** 表达，不创造事实。

它只读取已审计状态，生成：

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

## 5. 信息增益决策

Hypothesis Agent 为每个假设构造 `ActionCandidate`：

```text
action_id
hypothesis_id
action
expected_information_gain
estimated_cost
feasible
expected_discriminates
rationale
```

当前确定性策略：在可行动作中选择最大的 `expected_information_gain / estimated_cost`。当 synthetic case 同时存在多个直接 gap 时，当前优先级为：

```text
perceptionEvidence -> longitudinalPlan   0.90
longitudinalPlan -> carControl           0.80
carControl -> sendcan                    0.70
```

这不是“感知一定是根因”的规则；它只是面对同等成本的竞争直接异常时，优先验证更上游、能解释更多下游现象的动作。所有候选和选择都会写入 `decision_board.json`。

## 6. 两种执行路径

### 6.1 真实 openpilot-like 日志

```text
真实 rlog/qlog
→ 观测工具
→ suspected link / 证据不足
→ 若缺少可控基线：记录下一步需要的日志
→ Auditor
```

真实日志不会被 repair，也不会生成已验证根因。

### 6.2 受控 synthetic ADSLogRecord

```text
clean case → 注入 perception / planning / sendcan fault
→ 观测工具 → hypothesis board → 选择 repair
→ counterfactual replay → validation
→ synthetic-only validated_root_cause
```

当前测试覆盖 `perception_dropout`、`planner_gap`、`sendcan_gap` 与感知+sendcan 的歧义双故障场景。

## 7. 与 CARLA 的关系

`CarlaADSLogAdapter` 已定义统一的 ADSLogRecord 输入契约，但没有引入 CARLA runtime。后续 CARLA recorder 只需从闭环运行导出 `timestamp_s`、topic、payload summary 和 raw reference，即可复用同一套 Agent、hypothesis board、干预接口和 Auditor。只有 recorder 与真实闭环执行完成后，CARLA 才能成为“已验证 backend”。
