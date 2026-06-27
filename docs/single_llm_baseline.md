# Single-LLM Baseline

## Purpose

The Single-LLM baseline measures whether one language model can diagnose a scenario from the same deterministic
tool outputs used by the other methods. It is an experimental comparison, not the default product path.

The implementation uses the OpenAI Python SDK. The OpenAI config uses native Pydantic structured-output support
through the Responses API. Compatible providers can use Chat Completions plus local Pydantic validation. See the official
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).

## Leakage Boundary

`build_single_llm_input()` starts from `ScenarioRecord.observed_view()` and then produces an aggregate summary.
The API payload excludes:

- `oracle` and all true fault/root/time labels.
- `source.generation`, raw paths, raw log IDs, tokens, and scenario IDs.
- Free-text observed event descriptions and attributes.
- Metric `supports`, `contradicts`, and free-text descriptions.

The model receives metric names, numeric values, thresholds, timestamps, status, and evidence IDs. This preserves
the tool evidence while preventing rule labels from becoming answer hints.

## Output And Scoring

The model returns a strict `SingleLLMOutput`, which is converted to the common `DiagnosisRecord` schema. Allowed
fault labels and root modules are fixed, and inconsistent fault/root pairs are rejected by Pydantic.

The original deterministic evidence records are attached after the API call. LLM-generated evidence is never
accepted. Claims may cite supplied IDs, omit citations, or invent IDs; the evaluator scores the result directly:

- Valid supporting citation: covered and correct.
- Missing citation: uncovered and hallucinated.
- Unknown or non-supporting citation: covered but hallucinated.

This behavior is intentional so the baseline cannot silently repair its own unsupported output.

## Configuration

`configs/llm.yaml` contains only non-secret settings. API credentials come from environment variables:

```bash
export OPENAI_API_KEY='your-api-key'
export OPENAI_BASE_URL='https://example.com/v1'  # optional
```

API execution has two guards:

1. `enabled` defaults to `false` in the config.
2. The CLI requires `--enable-llm`, or `RUN_SINGLE_LLM=1` through `backend.sh`.

Use a small smoke run before the full 72-scenario benchmark:

```bash
python experiments/run_eval.py \
  --method single_llm \
  --dataset data/sample_scenarios/manual_json/v0_1 \
  --run-id manual_v0_1_single_llm_smoke \
  --enable-llm \
  --limit 5
```

Each diagnosis agent trace records the provider, model, endpoint, response ID, and available token usage. Secrets
and the API base URL are not written to run artifacts.

## DeepSeek

`configs/llm_deepseek.yaml` targets DeepSeek's OpenAI-compatible Chat Completions endpoint. It loads the following
variables from the ignored project `.env` without executing shell expressions:

```dotenv
DEEPSEEK_API_KEY='your-api-key'
DEEPSEEK_BASE_URL='https://api.deepseek.com'
DEEPSEEK_MODEL=deepseek-v4-pro
```

DeepSeek JSON Output accepts `response_format={"type":"json_object"}` rather than OpenAI's Pydantic
`json_schema` request shape. The client therefore includes the `SingleLLMOutput` JSON schema in the system prompt,
parses the returned JSON locally, and retries empty or schema-invalid content at most once. Semantic mistakes such
as an inconsistent fault/root pair are preserved for evaluation instead of being silently repaired. See DeepSeek's
official [JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/).

Use `--resume` for API runs. Completed per-scenario metrics and diagnoses are validated and reused, while missing
scenarios continue from the same run directory.

The first real 5-scenario smoke test completed with all API responses parsed and produced:

| Metric | Value |
| --- | ---: |
| Fault Accuracy | 0.4000 |
| Fault Macro-F1 | 0.2333 |
| Root Top-1 Accuracy | 0.6000 |
| Evidence Coverage | 1.0000 |
| Evidence Correctness | 0.6143 |
| Hallucination Rate | 0.1467 |

This smoke result validates the pipeline only; it is too small for a method-level conclusion. The 72-scenario run
is the reportable comparison.
