# Agent v2：诊断与优化智能体重新定义

日期：2026-07-05

## 1. 为什么必须重定义

当前代码中的 `MetricAgent`、`PerceptionAgent`、`PlanningAgent` 和 `ControlAgent` 实际执行固定函数：读取
预先计算的 evidence，按固定分数输出标签。它们具有模块化价值，但没有自主目标、假设更新、工具选择或
迭代行为，因此更准确的名字是 deterministic diagnostic nodes，而不是本项目最终要研究的 Agent。

LangGraph 官方也明确区分 workflow 与 agent：workflow 走预先确定的代码路径，agent 则根据反馈动态决定
过程和工具使用。[LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

本项目的 Agent v2 不再以“检查哪个模块”为定义，而以“完成一次可证伪的故障调查和优化验证”为目标。

## 2. Agent 的最低契约

一个组件只有同时具备以下六项，才称为 Agent：

1. **Goal**：本次运行要解决的目标，例如确认导致碰撞风险的最早可干预原因。
2. **Private State**：自己的工作记忆，包括已知事实、未决问题、工具结果和预算。
3. **Hypothesis Set**：一个或多个可被支持或证伪的候选机制，而不是单个标签分数。
4. **Action Space**：可以选择下一步调查、委派、实验、停止或拒答。
5. **Tool Allowlist**：只能调用注册工具，工具输入输出必须结构化且可追踪。
6. **Stop Condition**：达到证据门槛、完成验证、预算耗尽或确认不可诊断时结束。

Agent 每一步只能从下列动作中选择：

```text
PROPOSE_HYPOTHESIS
CALL_TOOL
DELEGATE_INVESTIGATION
REQUEST_MORE_EVIDENCE
REQUEST_COUNTERFACTUAL
CHALLENGE_HYPOTHESIS
PROPOSE_INTERVENTION
REQUEST_VALIDATION
ABSTAIN
FINALIZE
```

Parser、schema validator、TTC calculator、collision checker、perception matcher、fixed scorer、renderer、report
template 都是工具或服务，不再单独称为 Agent。

## 3. 共享 CaseState

多 Agent 围绕同一个版本化 `CaseState` 协作，但每个 Agent 只能写自己拥有的字段：

```text
CaseState
  case_id / run_id / sut_info / diagnosis_mode
  investigation_goal / incident_window / data_coverage
  observations[] / evidence[] / unresolved_questions[]
  hypotheses[] / causal_graph / investigation_tasks[]
  counterfactual_runs[] / optimization_candidates[] / validation_runs[]
  budget / iteration / agent_trace[] / stop_reason
```

核心 `Hypothesis` 不是一个分类标签，而是可验证对象：

```json
{
  "hypothesis_id": "H_003",
  "claim": "stale front-object track caused the planner to brake 0.7 s late",
  "target_component": "perception_tracker",
  "mechanism": "track update stopped while ego continued closing",
  "predicted_observations": [
    "track timestamp stops before planner response",
    "world reference distance continues decreasing"
  ],
  "required_evidence": ["track_age", "planner_first_brake_time"],
  "falsifiers": [
    "track remains fresh throughout the incident",
    "planner receives fresh obstacle state but still delays"
  ],
  "confidence": 0.42,
  "status": "active"
}
```

每次 confidence 变化都必须引用新增 evidence 或 counterfactual result，禁止只写“重新思考后提高置信度”。

## 4. 新的 Agent 角色

### 4.1 Case Manager Agent

**目标**：把事故调查推进到可停止状态，而不是自己猜根因。

**可做**：确定调查目标、维护 hypothesis board、选择需要的专家、分配预算、决定进入证伪/反事实/优化阶段。

**不可做**：直接修改 evidence、执行仿真、跳过 Critic 后定案。

**输出**：`investigation_plan`、任务依赖、当前阶段和停止原因。

### 4.2 Domain Investigator Agents

这是按需创建的专家池，不再无条件同时运行三个固定节点。首批 profile 包括：

- Perception Investigator：sensor、detector、tracker、fusion 的候选机制；
- Planning Investigator：行为决策、轨迹、安全约束和 stale input；
- Control Investigator：命令响应、执行器延迟、饱和和动力学偏差；
- 后续可增加 Localization、Prediction、Map、System Health Investigator。

**目标**：针对一个调查问题提出多个候选机制，主动选择工具，寻找支持证据和反证。

**停止条件**：问题已回答、候选均被证伪、缺少必要信号或达到工具预算。

**输出**：结构化 hypotheses、evidence links、falsifiers、remaining questions；不能输出全局最终根因。

### 4.3 Causal Reasoner Agent

**目标**：把模块调查结果转成时间有向因果图，区分 root、propagation、symptom 和 external hazard。

**工具**：timeline aligner、dependency graph、first-divergence detector、change-point detector。

**输出**：带 evidence_id 的因果边，例如：

```text
sensor frame drop @4.1
  -> stale track @4.2
  -> unsafe plan @4.6
  -> late brake @4.9
  -> collision @5.3
```

相关性或时间先后只能生成候选边，不能直接当成已验证因果边。

### 4.4 Critic Agent

**目标**：主动推翻当前 Top-1，而不是帮助它写得更像真的。

**动作**：检查循环论证、数据泄漏、替代解释、证据不一致、world reference 缺失、reference monitor 冒充
SUT、碰撞后果冒充根因等问题。

**输出**：`supported / weakened / falsified / not_testable`，以及下一项最有信息量的证据请求。

没有通过 Critic 的 hypothesis 不能进入最终报告。

### 4.5 Counterfactual Experiment Agent

**目标**：把“可能因为 X”转成“移除或改变 X 后，结果是否改变”。

**工具**：CARLA paired replay、nuPlan planner rerun、fault toggle、parameter sweep、first-divergence comparison。

**动作**：选择最小干预变量，生成实验 manifest，提交异步运行，读取结果并更新 hypothesis。

**约束**：不能读取 fault oracle 来决定答案；只有 evaluator 在实验后比较注入真值。

### 4.6 Optimization Agent

**目标**：针对已验证机制提出最小、可回滚、可测试的优化方案。

优化对象包括：

- detector/tracker threshold、timeout、association gate；
- planner safety cost、fallback condition、stale-input guard；
- controller gain、delay compensation、saturation protection；
- 数据补充、场景回流与回归测试配置。

每个 candidate 必须包含 target、config/code diff、预期改善、可能副作用、验证场景和回滚条件。第一版只
自动生成候选配置和 patch proposal，不直接修改生产系统。

### 4.7 Validation Agent

**目标**：执行优化前后 A/B 与回归集，拒绝只修好一个案例却破坏正常场景的方案。

**指标**：故障场景风险下降、healthy success、碰撞/违规、舒适性、误报率、计算延迟和回归失败数。

**输出**：`accepted / rejected / inconclusive`。没有 Validation 结果的内容只能叫建议，不能叫已验证优化。

### 4.8 Report Composer Service（不是 Agent）

**职责**：忠实序列化已通过 Critic/Counterfactual/Validation 的结果。

它没有独立 hypothesis/action loop，因此按本定义属于确定性服务。它不能产生新 hypothesis。报告必须
分开：已验证根因、未决候选、传播链、优化候选、验证结果和能力边界。

## 5. 协作状态机

```text
INGEST
  -> TRIAGE
  -> HYPOTHESIS_BOARD
  -> DOMAIN_INVESTIGATION (selected experts, parallel)
  -> CAUSAL_SYNTHESIS
  -> CRITIQUE
       -> insufficient evidence -> INVESTIGATION loop
       -> testable cause -> COUNTERFACTUAL loop
       -> not diagnosable -> ABSTAIN
  -> ROOT_CAUSE_GATE
  -> OPTIMIZATION
  -> VALIDATION
       -> failed -> OPTIMIZATION loop or stop
       -> passed -> FINAL_REPORT
```

这不是无限自治。默认限制最大 3 轮调查、2 次 counterfactual、3 个 optimization candidate 和总 token/tool
预算；预算耗尽时必须保留未决问题并输出 `uncertain`。

## 6. LLM、工具与确定性边界

Agent v2 中 LLM 的职责是：提出可证伪假设、选择下一工具、比较替代解释、生成优化候选。所有数值计算、
几何碰撞、日志读取、仿真执行、配置 diff 和指标评估仍由确定性工具完成。

首版建议：

- DeepSeek：Case Manager、Domain Investigator、Critic、Optimization policy；
- Python tools：Evidence、Causal、Counterfactual、Validation 的事实计算；
- Qwen-VL：仅作为按需视觉调查工具，不直接定根因；
- deterministic DAG：保留为不使用 LLM 的 baseline 和失败 fallback。

所有模型输出使用 Pydantic action schema，温度为 0；prompt/model/tool/config hash 与完整 action trace 必须
保存。Agent 不允许读取 `fault_oracle`。

## 7. 为什么现在需要 LangGraph

旧 DAG 是预定顺序 workflow，用 Pydantic 函数足够。Agent v2 出现调查循环、异步 CARLA 实验、预算停止、
人工批准优化和失败恢复后，持久化图才有实际价值。

LangGraph 的 persistence 会在步骤间保存 checkpoint，并支持 replay/fork；interrupt 可以暂停并等待人工
批准后继续。[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、
[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)

因此新的决定是：

- 旧 `DiagnosisGraph` 不重写，冻结为 `deterministic_workflow_v1` baseline；
- Agent v2 使用独立 `InvestigationGraph`，优先实现 in-memory checkpoint smoke；
- CARLA 运行和自动 patch 前设置 interrupt；
- 两条路径共享 Scenario/Evidence/Report schema，不要求输出完全相同，因为 Agent v2 增加 hypothesis、实验和优化状态。

## 8. Agent v2 的实验问题

不再只比较“最终分类准不准”，而回答：

1. 是否在 unseen compound fault 上提出包含真因的 Top-K hypothesis？
2. Critic 是否减少无证据根因和错误确认？
3. Counterfactual 是否提高 causal root Top-1，而不仅是相关性分类？
4. Optimization 是否降低故障场景风险且不破坏 healthy regression？
5. 动态工具选择是否以可接受成本减少不必要调用？

核心方法：

| 方法 | 作用 |
| --- | --- |
| Rule-only | 简单规则下限 |
| deterministic workflow v1 | 当前模块化固定流程 |
| Single-LLM | 无工具协作基线 |
| Agent v2 no critic | Critic 消融 |
| Agent v2 no counterfactual | 反事实消融 |
| Agent v2 diagnosis only | Optimization/Validation 消融 |
| Agent v2 full | 完整方法 |

新增指标：Hypothesis Recall@K、Falsification Precision、Verified Root Accuracy、Counterfactual Success、Repair
Success、Healthy Regression Rate、Average Tool Calls、Iterations、Token/Latency Cost、Abstention Accuracy。

## 9. 迁移原则

现有实现不删除，按以下方式重命名和复用：

| 当前组件 | Agent v2 中的新定位 |
| --- | --- |
| metric_agent | deterministic metric service |
| scene_agent | coverage/triage tool |
| perception/planning/control_agent | domain evidence tools，供 Investigator 调用 |
| root_cause_agent | deterministic workflow v1 aggregator |
| report_agent | Report Composer Service / deterministic renderer |
| visual_review_agent | Investigator 的可选视觉工具 |
| failure_sample_builder | regression/data feedback service |

第一步不是立刻改所有代码，而是先冻结 `AgentAction`、`Hypothesis`、`InvestigationTask`、`CounterfactualRun`、
`OptimizationCandidate`、`ValidationResult` 和 `InvestigationState` 七个 schema，再实现单场景最小循环。
