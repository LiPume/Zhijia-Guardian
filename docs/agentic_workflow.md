# Agentic 工作流

离线图是显式代码，而不是把一组普通 Python 函数重新命名为 Agent：

```text
开始 → 读取 observed case → Case Manager
     → 条件分派专业 Agent（消息 / CAN / 控制 / 安全）
     → Hypothesis → Counterfactual → Validation
     → Evidence Auditor → Report Agent → 结束
```

每个角色都有诊断目标、局部状态和受限工具面。Case Manager 在本地保存发现的 topic 和请求的 Agent；专业 Agent 返回结构化 `AgentRun`。工作流会在 `agent_trace.json` 中记录工具、假设、evidence ID、输出与停止条件。

图会在专业 Agent 完成后，或提前触及 `max_agent_rounds` / `max_tool_calls` 时停止；审计与报告步骤仍会执行。`LLM_PROVIDER=openai` 仅在存在 `OPENAI_API_KEY` 时启用；它只能选择已注册工具，仍必须通过 Auditor。缺失或不支持的凭据会确定性退化为离线路由。
