# 审稿结论与算法改进计划

状态日期：2026-07-14。本文是当前实现的审稿式自评与下一阶段的**算法优先**计划；它不把尚未完成的改进表述为既有能力。

## 一句话结论

这个架构值得继续做：作为本科科研原型、保研展示和可复现工程，当前可评为 **7.5/10**；作为可主张方法有效性的论文工作，当前约为 **5/10**。它已经从“多个 Agent 自由讨论根因”的叙事，收敛为 evidence-bounded 的诊断工作流；但尚不足以证明多 Agent 决策本身比固定规则或固定 pipeline 更有效。

因此下一阶段的目标不是“再加 Agent 或做漂亮界面”，而是把现有的架构合理性变成可被反驳、可比较、可测量的方法证据。

## 目前成立的部分

1. **真实性边界正确。** 真实 rlog/qlog 只给出 `suspected_link`、`insufficient_evidence` 或 `cannot_determine_root_cause`；oracle 与 observed data 隔离。
2. **工具与推理职责正确。** 频率、gap、时间戳、CAN 和控制一致性由确定性工具计算，Agent 只能选择已注册工具、管理假设和组织调查。
3. **Evidence Auditor 有实质作用。** 它检查 evidence 引用、观测边界和跨数据源错误拼接，并可以降级结论。
4. **已有闭环雏形。** synthetic 输入可执行“异常发现 → 假设 → repair/replay → validation”，这比对同一日志做多角色文本总结更接近诊断。

## 当前不能成立的主张

- 不能声称系统恢复了真实 openpilot 车辆事故的根因。
- 不能声称多 Agent 一定优于线性 pipeline；目前尚无基线和消融证据。
- 不能把无 DBC 的 CAN 地址统计称为车辆控制语义诊断。
- 不能把 nuScenes、nuPlan 和 openpilot 主路线拼成一条真实端到端因果链。
- 不能把“从 clean baseline 恢复被删除消息后 gap 消失”直接称为系统级根因验证。

## 主要审稿风险与处置

| 风险 | 当前问题 | 必须完成的改进 |
| --- | --- | --- |
| 伪多 Agent | Validation、Auditor、Report 主要是固定节点 | 保留 4–5 个具备局部目标、可选工具与条件分支的调查 Agent；其余改为受调用基础设施。 |
| 手工信息增益 | `0.90/0.80/0.70` 是人工常数 | 先改名为 `diagnostic_priority_score`；完成概率预测后再用严格 IG。 |
| 循环证明 | repair 的对象正是先前删除的数据 | 加 paired、sham、alternative repair；要求目标与下游预测同时兑现。 |
| 多故障歧义 | 目前主要沿上游单链找解释 | 显式比较传播、独立、共同原因与不可观测四类假设。 |
| CAN 语义不足 | 无车型 DBC 时只能得到帧统计 | 固定能力边界为通信健康；可选引入车型绑定 DBC profile。 |
| 辅助证据混淆 | 自定义 `perceptionEvidence` 容易被误解为原生 topic | 主图仅保留原生 openpilot topic；辅助证据仅进入 `AuxiliaryEvidenceBundle`。 |
| 固定 DAG | 每个案例若都跑同一串节点，多 Agent 没有必要 | 以工具预算、熵/不确定性、可观测性与预期区分度驱动路由，并用 trace 证明分支差异。 |

## 算法改进路线

### 阶段 A：先把结论与数据边界校正

1. 将 synthetic 的强结论从 `validated_root_cause` 改为 `counterfactually_supported_injected_fault_location`（简称 CSIFL）。它表示“注入的故障位置在受控对照中得到支持”，不是现实系统的终极根因。
2. 仅当以下条件都满足时，允许报告更强的“支持传播机制”措辞：
   - repair 后目标异常消失；
   - 预先登记的至少一个下游异常也恢复；
   - sham repair 不产生同样恢复；
   - alternative repair 对竞争假设的预测不同；
   - 所有判断都引用 observed evidence，oracle 只供离线 evaluator 打分。
3. 将辅助 topic 改为命名空间形式，例如 `zgAux.perceptionEvidence`；它不进入 native openpilot dependency graph。原生主图优先采用实际存在的 `modelV2`、`drivingModelData`、`longitudinalPlan`、`carControl`、`sendcan`、`carState` 等 topic。

### 阶段 B：从固定映射到竞争假设图

针对同一异常集合，Hypothesis Investigation Agent 至少生成四类可证伪假设：

```text
Propagation:       A 的异常经依赖边 A → B 传播
Independent:       A 与 B 是两个独立故障
Common-cause:      未观测共同上游 C 同时影响 A 与 B
Unobservable:      当前日志不足以区分上述解释
```

每个假设必须带有：支持/反驳 evidence、预期时间顺序、预期受影响节点、可执行检查或干预、失败/停止条件。这样“感知 gap + sendcan gap”不会被机械地解释为单一上游故障。

### 阶段 C：可解释的动作选择

在尚无经过校准的概率模型前，使用可审计的优先级，不滥用“信息增益”名称：

```text
diagnostic_priority_score(a) =
  evidence_strength(a)
  × downstream_explanatory_coverage(a)
  × discriminability(a)
  × feasibility(a)
  / execution_cost(a)
```

各项必须可追溯：

- `evidence_strength`：gap 严重度、跨工具一致性、时间顺序一致性；
- `downstream_explanatory_coverage`：依赖图中能被该假设解释的观测节点比例；
- `discriminability`：该动作能让多少竞争假设产生不同预测；
- `feasibility`：是否有相应 topic、clean baseline、replay 或 simulator；
- `execution_cost`：工具调用数、需要的额外数据和运行时间。

当后续为每个假设建立 `P(outcome | hypothesis, action)` 时，才使用严格的条件熵信息增益：

```text
IG(a) = H(H | E) - Σ_o P(o | E, a) H(H | E, o)
```

并以 `IG(a) / cost(a)` 选择动作。早期概率可来自 synthetic fault matrix 的频率估计，并在报告中附校准误差；不能再使用无来源的固定常数。

### 阶段 D：让 Agent 真正产生可变执行路径

建议保留的调查 Agent：

| 角色 | 局部决策 |
| --- | --- |
| Case Manager | 从可用 topic、预算和不确定性中选择调查分支或直接拒答 |
| Message Flow Investigator | 选择频率、gap、stale、同步等少量必要工具 |
| CAN Investigator | 仅在 `can/sendcan` 可用且能区分假设时运行帧级检查 |
| Control & Safety Investigator | 根据 control/safety topics 选择一致性、响应或 safety 检查 |
| Hypothesis Investigation Agent | 更新竞争假设、选择下一检查或建议停止 |

应降级为基础设施的组件：`CounterfactualExecutor`、`ValidationTool`、`EvidenceAuditor`、`ReportRenderer`。它们仍非常重要，但不应仅因位于 DAG 节点就被包装成“自主 Agent”。

验收方式不是角色数量，而是 trace 差异。例如消息单 topic gap 可以在 Auditor 前停止 CAN/控制检查；控制-安全冲突可以跳过无关的感知检查并进入竞争假设与 validation。测试应断言不同 case 的已调用工具集合不同。

### 阶段 E：反事实验证不再循环证明

每项 synthetic 注入至少执行下列对照：

1. **fault replay**：带注入故障的记录；
2. **targeted repair**：只恢复被假设指向的链路；
3. **sham repair**：恢复一个不应影响该假设的相似 topic/时间窗；
4. **alternative repair**：修复竞争假设对应链路；
5. **downstream check**：检查预注册的下游异常是否按预测改善。

结论由对照差异决定，而不是“恢复原始消息，所以原始消息又存在”的同义反复。对于只造成单 topic 缺失、没有可观测下游效应的样例，输出应保守为 `confirmed_fault_location`，而非传播根因。

### 阶段 F：CAN 语义能力分层

无 DBC profile：输出 `CAN communication health`（地址覆盖、频率、gap、burst、bus 分布），报告明确拒绝解释车辆物理量。

有合法且车型匹配的 DBC profile：在独立的 `VehicleSignalDecoder` 中解码明确的信号，并记录 profile 版本、车型、bus 与解码失败率；此功能不应成为运行 MVP 的强依赖。

## 评估设计：从“能跑”到“方法成立”

建立小而严格的 synthetic/CARLA-compatible fault matrix，而非下载大数据集：

- 单点：消息 gap、delay、stale、CAN gap、`carControl/sendcan` 不一致、安全层阻断；
- 传播：感知/规划/控制/底层各一类可预期下游效应；
- 多故障：独立双故障、共同原因代理、相邻链路竞争故障；
- 观测缺失：移除关键 topic，考核是否正确拒答。

至少比较：

1. 固定顺序 pipeline（与本系统使用完全相同的工具）；
2. 规则 first-match baseline；
3. 动态路由但不使用竞争假设；
4. 完整方法；
5. 完整方法去掉 Auditor 的消融。

报告指标：fault-location Top-1/Top-k、错误强结论率、`insufficient_observability` 的 precision/recall、finding evidence 完整率、置信度 ECE/Brier、平均工具调用数/时延、干预成功率、以及多故障的假设区分准确率。真实 rlog/qlog 只评估工具覆盖、稳定性、拒答质量与 evidence 完整性，不用伪造根因 accuracy。

## 展示层的安排

前端被明确排在算法验收之后。届时做一个零依赖本地工作台，加载已有 artifact，展示消息缺口、竞争假设、动作选择、repair 对照、审计降级和 agent trace。它只做展示，不参与诊断计算、不上传日志、不读取 API Key。最直观的 demo 应是“targeted repair 与 sham repair 的下游差异”，而不是仅展示漂亮的 Agent 方框。

## 论文/保研可用表述

推荐表述：

> Zhijia-Guardian 是一个面向 openpilot-like 消息流与控制链路的、evidence-bounded 的离线诊断原型。它使用确定性工具获取事实，以依赖图和可观测性约束多 Agent 的调查路由；真实日志只定位疑似异常链路，受控 synthetic 场景才用于验证注入故障位置。

避免表述：

> 系统可自动恢复真实 ADS 事故根因，或多 Agent 必然优于线性 pipeline。
