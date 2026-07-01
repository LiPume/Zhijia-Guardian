# Agent Orchestration Decision

## Decision

Keep the current explicit Pydantic diagnosis DAG as the default MVP orchestrator. Do not add LangGraph as a
runtime dependency only to rename existing nodes.

The current graph already provides the requirements exercised by the benchmark:

- typed shared state;
- metric/scene preparation;
- perception, planning, and control fan-out;
- root-cause fan-in with causal time ordering;
- unavailable-module skipping;
- deterministic execution trace;
- physical removal of oracle data before graph execution.

## When LangGraph Becomes Useful

Add an optional LangGraph backend when at least one of these product requirements is implemented:

1. an engineer can pause a diagnosis, approve/edit evidence, and resume it;
2. jobs must survive process restarts with durable checkpoints;
3. failed remote LLM/tool nodes need persisted retry and replay;
4. long-running diagnoses need time travel or state inspection across workers;
5. multiple deployment services must resume the same graph run.

At that point, wrap the existing typed node functions rather than rewriting diagnosis logic. Both backends must
produce the same `diagnosis_v1` record and pass parity tests on frozen scenarios.

## Non-Goals

- Free-form Agent chat is not the orchestration model.
- LangGraph is not an experimental independent variable; the contribution is module diagnosis plus evidence and
  temporal root-cause ranking.
- Adding framework overhead without persistence, interrupts, or distributed execution does not improve the
  current offline benchmark.
