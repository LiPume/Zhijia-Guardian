# Agentic workflow

The offline graph is explicit code, not a renamed list of Python functions:

```text
START → ingest observed case → Case Manager
      → conditional specialist dispatch (message / CAN / control / safety)
      → Evidence Auditor → Report Agent → END
```

Each role declares a diagnostic objective, local state and a bounded tool surface. The case manager persists discovered topics and requested specialists locally. Specialists return structured `AgentRun` values. The workflow records tools, hypotheses, evidence IDs, outputs and stop conditions in `agent_trace.json`.

The graph stops after dispatched specialists, or earlier at `max_agent_rounds`/`max_tool_calls`; auditor and report steps still run. `LLM_PROVIDER=openai` is recognized only with `OPENAI_API_KEY`; it is constrained to the same registered tool schema and must still pass the auditor. Missing/unsupported credentials deterministically downgrade to offline routing.
