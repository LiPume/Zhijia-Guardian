# 设计说明

`DiagnosticCase` 替代 `ScenarioRecord`。它校验单一来源、时间范围、service catalog、带时间戳的消息摘要、依赖图、观测、工具结果、evidence、finding、限制与可选的仅评估端 oracle。消息 payload 只保存摘要和 raw reference，不会把原始 rlog payload 复制到报告。

observed data 与 `oracle` 通过 `DiagnosticCase.observed_copy()` 分离。任一 Agent 调用前，workflow 都构造不含 oracle 的视图；oracle 仅保留在 clean/perturbed 输入中，供评估端检查。

每个工具返回 `ToolResult(tool_name, status, time_window, metrics, evidence, limitations)`。每条 evidence 都有每次运行稳定的 ID；每个 finding 至少引用一个 evidence ID。没有受控验证时，finding 只能是 suspected link 或证据不足；只有 synthetic 的 targeted/sham/alternative 对照均符合预测，Auditor 才允许 `counterfactually_supported_injected_fault_location`，且该结论不等同于真实根因。

`AuxiliaryEvidenceBundle` 用于 nuScenes 感知证据和 nuPlan 规划证据。它固定带有 `same_route_as_primary=false`，因此不能成为真实主路线因果结论的替代证据。
