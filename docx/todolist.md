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
