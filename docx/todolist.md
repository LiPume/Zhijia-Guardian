# 主动因果诊断待办

状态日期：2026-07-14

- [x] 在 `legacy-before-openpilot-recalibration` 保存旧版实现。
- [x] 审计既有代码、文档、测试、Git 状态与可复现性风险。
- [x] 移除旧 CARLA/nuScenes/nuPlan 优先的 workflow 代码和过期生成 demo。
- [x] 定义 Pydantic `DiagnosticCase`、evidence、finding 和 tool-result 契约。
- [x] 增加独立 openpilot rlog/qlog adapter 与最小 synthetic openpilot-like adapter。
- [x] 实现确定性的消息流、CAN、控制链路、安全与 evidence 工具。
- [x] 实现带状态、受限路由和 trace 输出的工具使用型多 Agent workflow。
- [x] 增加可复现 CLI、数据根配置、最小数据获取/检查脚本与输出打包。
- [x] 在外部数据根浅克隆 openpilot，并验证真实日志 smoke 路径。
- [x] 运行扰动样例 demo 和测试，并如实记录限制。
- [x] 重写项目文档，包含数据边界与旧版重校准理由。
- [x] 提交检查点、检查跟踪文件，并通过正常方式推送 `main`。

## 主动多 Agent 扩展

- [x] 明确主诊断/辅助/验证证据边界：openpilot-like 日志是主输入；nuScenes 和 nuPlan 是 adapter，绝不声称为同一路线。
- [x] 增加 hypothesis board、intervention、validation 与 evidence bundle 的 Pydantic 契约。
- [x] 不下载完整数据集，增加归一化 nuScenes 感知与 nuPlan 规划 evidence adapter。
- [x] 增加带 repair/replay 和反事实验证工具的 synthetic 干预沙箱。
- [x] 增加主动路由：形成假设 → 选择价值最高的可行检查/干预 → 观察结果 → 更新置信度/停止。
- [x] 扩展审计/报告 artifact，加入假设图、决策理由、干预结果与来源边界检查。
- [x] 增加 synthetic 验证成功、真实案例不干预、跨数据集证据隔离测试。
- [x] 提交并推送主动扩展。

## 决策质量与 CARLA-compatible 扩展

- [x] 显式建模竞争假设和动作候选，包含预期信息增益与成本。
- [x] 使用确定性的预期信息增益选择，替代 first-match 干预选择。
- [x] 不引入 CARLA runtime 依赖，增加 CARLA-compatible 归一化 ADSLogRecord adapter。
- [x] 增加歧义场景，验证一次干预可区分竞争假设。
- [x] 输出 decision-board artifact，并记录下一步 CARLA runtime 集成边界。
- [x] 运行测试/demo、提交并推送。

## 审稿风险驱动的算法改进（下一阶段）

> 这一阶段优先验证“方法是否成立”，不以增加 Agent 数量或前端展示为目标。详见 [`docs/review_and_algorithm_plan.md`](../docs/review_and_algorithm_plan.md)。

- [ ] 将 `validated_root_cause` 重命名并降级为 `counterfactually_supported_injected_fault_location`；只有多节点下游预测同时兑现时，才允许更强的机制性表述。
- [ ] 把当前手工固定的 `expected_information_gain` 改为可追溯的 `diagnostic_priority_score`；完成竞争假设的条件概率建模后，再恢复严格的信息增益定义。
- [ ] 拆分“原生 openpilot 依赖图”和 `AuxiliaryEvidenceBundle`；将 `perceptionEvidence` 明确为 `zgAux.*` 辅助 topic，避免混入原生消息链路。
- [ ] 增加四类竞争假设：传播、独立双故障、共同原因、可观测性不足，并让每类假设给出可区分的预测。
- [ ] 让 Case Manager 与专业 Agent 基于证据预算和不确定性动态选择/跳过工具；为不同案例记录不同 trace，并加回归测试防止退化成固定 DAG。
- [ ] 将 Counterfactual Executor、Validation Tool、Evidence Auditor、Report Renderer 从“凑数量 Agent”降为受调用的基础设施；保留真正有分支与局部策略的调查 Agent。
- [ ] 实现 paired/sham/alternative repair 对照，并以目标链路与下游恢复共同验证注入故障位置，避免循环证明。
- [ ] 为 CAN 增加可选、车型绑定的 DBC profile；没有 profile 时固定输出为通信健康诊断，不声称车辆信号语义根因。
- [ ] 建立可控故障矩阵、固定 pipeline/规则基线与消融实验，报告定位、拒答、校准、证据完整性、工具成本等指标。

## 展示层（算法验证后再做）

- [ ] 实现零依赖本地诊断工作台：加载 `diagnosis.json`、`evidence.jsonl` 与 `agent_trace.json`，直观展示消息缺口、假设—干预—验证闭环和结论边界。
- [ ] 使用一个已验证的 synthetic `sendcan` gap artifact 作为静态 demo；页面不得上传日志、不得读取 API Key、不得将 synthetic 结果表述为真实车辆结论。
