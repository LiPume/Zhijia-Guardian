# Design

`DiagnosticCase` replaces `ScenarioRecord`. It validates a single source, time range, service catalog, summaries of timestamped messages, dependency graph, observations, tool results, evidence, findings, limitations, and optional evaluator-only oracle. Message payloads are summaries plus raw references; raw rlog payloads are never duplicated into reports.

Observed data and `oracle` are separated by `DiagnosticCase.observed_copy()`. The workflow constructs this oracle-free view before any agent is invoked. The oracle is only retained in clean/perturbed input files for evaluator inspection.

Every tool returns `ToolResult(tool_name, status, time_window, metrics, evidence, limitations)`. Every evidence record gets a stable per-run ID; every finding has at least one evidence ID. A finding is a suspected link, not a root cause, unless the evidence auditor can justify the narrower conclusion—which this MVP deliberately does not claim.
