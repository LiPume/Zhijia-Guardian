# Agent Orchestration Decision

## Decision Update: 2026-07-05

The repository now separates two methods instead of treating the existing fixed graph as the final multi-Agent
system.

1. `DiagnosisGraph` remains a Pydantic deterministic workflow and is frozen as `deterministic_workflow_v1`.
2. Agent v2 will use a separate LangGraph `InvestigationGraph` for hypothesis-driven diagnosis and optimization.

The old graph is not deleted. It remains the reproducible no-LLM baseline, tool integration test, and fallback when
the policy model or remote services are unavailable.

## Why The Old Graph Is A Workflow

The current execution path is predetermined:

```text
metric -> scene -> perception/planning/control -> root cause -> report
```

Its typed state, module gating, temporal ranking, evidence trace, and oracle isolation are valuable, but every case
runs the same nodes in the same order. The module functions do not maintain hypotheses, choose among tools, request
new evidence, or revise their plan after observations. They are deterministic diagnostic nodes.

## Why Agent v2 Uses LangGraph

Agent v2 introduces behavior that the fixed workflow intentionally lacks:

- a hypothesis board and per-Agent working state;
- dynamic delegation to relevant domain investigators;
- investigation and critique loops;
- asynchronous CARLA/nuPlan counterfactual experiments;
- optimization and regression-validation loops;
- budget-based stopping and safe abstention;
- human approval before expensive simulation or applying a patch proposal;
- checkpoint resume after remote model, tool, or simulator failures.

LangGraph is useful here because the product requirement now includes cyclic state transitions, persistence,
interrupt/resume, replay, and state forks. This is an orchestration choice, not evidence that Agent v2 is more
accurate.

## Separation Of Responsibilities

| Component | Responsibility |
| --- | --- |
| Pydantic models | Validate AgentAction, Hypothesis, Evidence, experiment, optimization, and validation records |
| LangGraph | Persist and route Agent v2 state, loops, interrupts, and asynchronous task results |
| DeepSeek policy | Propose hypotheses, select allowed actions/tools, critique alternatives, propose optimization |
| Python tools | Compute metrics, read logs, compare trajectories, execute replay, and evaluate regression |
| Qwen visual tool | Optional visual evidence acquisition when explicitly requested |
| Evaluator | Read fault oracle after the run and compute research metrics |

## Required Safety Rules

1. The Agent state never contains `fault_oracle`.
2. Every action follows a Pydantic schema and an Agent-specific tool allowlist.
3. Confidence changes require new evidence or counterfactual result IDs.
4. CARLA execution, high-cost multimodal calls, and patch application can require an interrupt approval.
5. Tool side effects are idempotent because interrupted nodes may restart.
6. Budget exhaustion ends in `ABSTAIN`, not an unsupported root cause.
7. Optimization is not `verified` until the Validation Agent passes fault A/B and healthy regression.

## Implementation Order

1. Freeze and rename the current method in documentation as `deterministic_workflow_v1`.
2. Define the Agent v2 state and action schemas without installing a framework.
3. Add LangGraph as a versioned optional dependency in the existing `yolo` environment.
4. Implement one in-memory, one-scenario investigation/critique loop.
5. Add checkpoint persistence and a fake counterfactual tool in tests.
6. Connect real CARLA paired replay only after the state machine is stable.
7. Add Optimization/Validation and human approval last.

## Evaluation Boundary

Agent v2 must be compared with Rule-only, `deterministic_workflow_v1`, Single-LLM, no-Critic, no-Counterfactual,
and diagnosis-only ablations. LangGraph adoption, number of agents, or trace length is not an independent success
metric. The claimed contribution must come from better verified hypotheses, causal tests, repair success, or safer
abstention.
