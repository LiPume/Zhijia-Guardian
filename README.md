# Zhijia-Guardian（智驾卫士）

> **Zhijia-Guardian: a tool-augmented multi-agent diagnostic workflow for message flows and control chains in openpilot-like ADS.**

智驾卫士不是“通用事故根因判定器”。它针对 openpilot-like 离线消息时间线，以确定性日志工具计算事实；Agent 会形成可证伪假设、选择下一项检查或 synthetic intervention、比较预测与结果，并由 Evidence Auditor 阻止无证据结论。

## 解决的问题与边界

研究对象是 rlog/qlog 或兼容输入中的 `can` / `sendcan`、`carState`、`carControl`、`controlsState`、`selfdriveState`、planner-related messages、`pandaStates`、`onroadEvents` 和消息频率、缺失、延迟、依赖与控制传递关系。系统可定位**异常消息链路或控制链路的 suspected link**；没有可观测证据时会输出 `insufficient_observability`、`insufficient_evidence` 或 `cannot_determine_root_cause`。

它不覆盖所有自动驾驶系统，不替代工程师，不从公开日志恢复真实事故根因，也不宣称多 Agent 一定优于线性 pipeline。

特别说明：**nuScenes、nuPlan、commaCarSegments 不能组成同一条真实端到端路线。**旧版相关模块已从主流程移除。

## 为什么是 tool-use 多 Agent

LLM（可选）不直接看日志猜根因：工具计算消息间隔、CAN 地址、控制链路一致性和安全事件；Agent 维护 hypothesis board、选择注册工具和停止条件；Auditor 审核 evidence ID 与可观测范围；Report Agent 只能渲染已有结构化状态。默认 `LLM_PROVIDER=none`，因此 CI 和 demo 不需要 API key。`LLM_PROVIDER=openai` 或 `LLM_PROVIDER=deepseek` 可使用一次 OpenAI-compatible 的结构化 `select_specialists` 工具调用，且缺 key、网络失败或非法工具结果都会自动降级为 offline 模式。

```text
rlog/qlog ── OpenpilotLogAdapter ── DiagnosticCase (oracle hidden)
                                      │
START → Case Manager → conditional specialists → Hypothesis Agent
                         ├ message flow tools
                         ├ CAN tools
                         ├ control-link tools
                         └ safety/interface tools
                                      │
               Counterfactual Agent → Validation Agent → Evidence Auditor → Report Agent
```

## Agents and tools

| Agent | Diagnostic target | Registered deterministic tools |
| --- | --- | --- |
| Case Manager | inventory and routing | topic catalog, dependency graph |
| Message Flow | frequency/gap/stale/order | topic frequency, gaps, timestamp discontinuity, stale check |
| CAN Diagnostic | CAN/sendcan coverage | frame extraction, address summary/frequency, CAN gap |
| Control Link | command propagation | control-response, carControl→sendcan, sendcan→carState, first divergence |
| Safety / Vehicle Interface | safety blocks/events | panda state and onroad event extraction |
| Hypothesis / Counterfactual / Validation | active causal debugging | hypothesis formation, synthetic repair/replay, prediction validation |
| Evidence Auditor | evidence-bound claims | evidence-reference validation, source-boundary and root-cause checks |
| Report Agent | factual rendering only | diagnosis/report/package writer |

The workflow has explicit state, conditional dispatch, agent-local state, structured output, trace records, and limits (`max_agent_rounds=3`, `max_tool_calls=30`).

## Cross-source evidence boundary

| Role | Source | Permitted use |
| --- | --- | --- |
| Primary diagnosis | openpilot-like / commaCarSegments | message, CAN and control-chain evidence for an individual route/segment |
| Auxiliary perception evidence | nuScenes | normalized perception-evidence adapter; never asserted as the same primary route |
| Auxiliary planning evidence | nuPlan | normalized planning-evidence adapter; never asserted as the same primary route |
| Causal validation | synthetic ADSLogRecord; CARLA next | controlled fault injection, repair/replay and oracle-only evaluation |

Only the controlled validation layer may emit `validated_root_cause`, and it means a validated injected mechanism for that synthetic case—not a real vehicle incident cause. The current runnable sandbox is synthetic ADSLogRecord; CARLA is intentionally the next backend, not a completed claim.

## Quick start

```bash
cd /home/lzx/Zhijia-Guardian
conda env create -f environment.yml  # or reuse the existing Zhijia environment
conda run -n Zhijia pip install -e '.[dev,openpilot]'
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
conda run -n Zhijia python scripts/run_agentic_demo.py --config configs/demo.yaml
```

The repeatable demo creates a clean openpilot-like timeline, deletes a bounded `sendcan` window, hides the perturbation oracle from all agents, and writes:

```text
$ZHIJIA_DATA_ROOT/outputs/synthetic-openpilot-perturbed/
├── diagnosis.json
├── evidence.jsonl
├── agent_trace.json
├── report.md
└── failure_sample_package/manifest.json
```

Expected result: the synthetic `sendcan` gap creates a testable `carControl -> sendcan` hypothesis; a repair replay removes the gap and produces `validated_root_cause` for that injected synthetic mechanism only. The output also includes `hypotheses.json` and `interventions.json`.

`decision_board.json` records the competing hypotheses, feasible actions, expected information gain/cost, and the selected action.

## Real openpilot logs and data policy

The upstream reference is external and never committed:

```bash
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
bash scripts/setup_openpilot_reference.sh
export OPENPILOT_ROOT=$ZHIJIA_DATA_ROOT/reference/openpilot
conda run -n Zhijia python scripts/inspect_openpilot_log.py /path/to/one.rlog.zst --openpilot-root "$OPENPILOT_ROOT"
```

`OpenpilotLogAdapter` uses upstream `openpilot.tools.lib.logreader.LogReader`; no openpilot source is copied or modified. Fetch only one explicit rlog/qlog segment (no camera video unless necessary), place it under `$ZHIJIA_DATA_ROOT/raw/openpilot/`, and keep it out of Git. `scripts/fetch_minimal_sample.py` documents the official small qlog smoke source.

## Current status and limitations

- Implemented: deterministic offline workflow, synthetic perturbation demo, Pydantic contracts, evidence audit, report/package artifacts, and independent real-log adapter.
- In progress: current official single-qlog smoke download and parsing validation. Real qlog topic availability varies due to qlog decimation; missing control/CAN topics are reported rather than fabricated.
- Not a benchmark or vehicle validation. Synthetic oracle is evaluator-only and does not establish real-world diagnostic accuracy.

See [docs/design.md](docs/design.md), [docs/active_causal_workflow.md](docs/active_causal_workflow.md), [docs/data_sources.md](docs/data_sources.md), [docs/limitations.md](docs/limitations.md), and [docs/legacy_recalibration.md](docs/legacy_recalibration.md).
