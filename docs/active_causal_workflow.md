# 主动因果工作流

此前的工具工作流是必要的事实底座，但不是项目最终贡献。本扩展实现了受限的诊断决策闭环：

```text
主路线观测 → 专业 Agent 证据 → hypothesis board
  → 选择价值最高且可执行的动作
  → synthetic repair/replay，或明确记录可观测性缺口
  → 比较预测与实际效果 → 更新 finding → 审计
```

Counterfactual Executor 当前只能在可控的 synthetic ADSLogRecord 沙箱中执行；同一接口为后续 CARLA 后端预留。它只能调用注册的 targeted/sham/alternative repair 工具，不能读取注入故障 oracle。面对真实 rlog/qlog，动作会是 `not_feasible`，或根本不选择动作；系统会请求补充进程/安全日志，而不是修改真实记录。

`counterfactually_supported_injected_fault_location` 的含义被刻意限制为：targeted repair 消除目标 gap，且 sham/alternative repair 保留该 gap。真实 openpilot route 永远不能使用该分类；这一结果也不自动证明真实根因或未观测传播机制。

决策面板使调查选择可审计。每个候选动作记录可行性、证据强度、下游覆盖、竞争假设区分度和成本。当前确定性策略选择最大的 `diagnostic_priority_score / cost`，不再使用无校准来源的“预期信息增益”常数；完成条件概率模型后才会改用严格的信息增益。

## CARLA 边界

`CarlaADSLogAdapter` 已支持紧凑导出的 ADSLogRecord（`timestamp_s`、topic、payload summary、raw reference），但不依赖 CARLA Python/runtime。下一步是让 CARLA recorder 从真实闭环运行中导出该契约；在此之前，项目不会将 CARLA 表述为已经执行的后端。

nuScenes 与 nuPlan adapter 会产出 `AuxiliaryEvidenceBundle`，并固定写入 `same_route_as_primary=false`。它们可用于 adapter 能力研究和感知/规划调查路由；Evidence Auditor 会记录来源边界警告，阻止任何“它们补全了主路线因果链”的说法。
