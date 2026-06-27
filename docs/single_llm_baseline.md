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
fault labels and root modules are fixed. Semantic inconsistencies between an allowed fault and root pair are
preserved so the evaluator can count them instead of silently repairing model mistakes.

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

This smoke result validates the pipeline only; it is too small for a method-level conclusion.

## Full 72-Scenario Result v0.1

The reportable run is `manual_v0_1_noisy_single_llm_deepseek_v4_pro_seed42` at commit `3691b8f`:

| Metric | Value |
| --- | ---: |
| Fault Accuracy | 0.5694 |
| Fault Macro-F1 | 0.4156 |
| Root Top-1 Accuracy | 0.7361 |
| Fault Start Time MAE | 0.3511 |
| Evidence Coverage | 1.0000 |
| Evidence Correctness | 0.7286 |
| Hallucination Rate | 0.1412 |

The 72 successful responses recorded 127,596 input tokens and 151,321 output tokens. Sixty-nine scenarios parsed
on the first attempt and three required the configured second JSON attempt, for 75 API attempts in total. Token
usage from the three discarded invalid first responses is not included. The complete run took about 29.2 minutes.

The dominant confusions were systematic rather than random:

- All 12 `perception_confidence_drop` scenarios were classified as `perception_miss`.
- Eleven of 12 `control_delay` scenarios were classified as `planning_collision_risk`; one was `uncertain`.
- Four normal boundary scenarios were classified as `planning_collision_risk`.

This supports using the LLM as an optional report or evidence-organization layer, not as the sole root-cause
classifier. It does not establish real-road generalization because the benchmark is still generated from the
canonical manual simulator.

## Full 72-Scenario Result v0.2

After replacing circular collision envelopes with oriented vehicle rectangles, the reportable v0.2 run is
`manual_v0_2_noisy_single_llm_deepseek_v4_pro_seed42` at commit `48f0578`:

| Metric | Value |
| --- | ---: |
| Fault Accuracy | 0.7500 |
| Fault Macro-F1 | 0.6169 |
| Root Top-1 Accuracy | 0.9028 |
| Fault Start Time Coverage | 0.8667 |
| Fault Start Time MAE @ Correct Fault | 0.2645 |
| Fault Start Time Coverage @ Correct Fault | 0.8261 |
| Evidence Coverage | 1.0000 |
| Evidence Correctness | 0.6827 |
| Hallucination Rate | 0.1331 |

The successful responses recorded 127,572 input and 156,093 output tokens. Seventy scenarios parsed on their
stored first attempt and two on a second attempt. One run interruption caused by two consecutive empty JSON
responses was recovered with `--resume`; discarded-response token usage is not included.

The geometry correction removed the dominant control/planning confusion: 11 of 12 `control_delay` scenarios are
now correct. The remaining systematic weakness is subtype separation: 11 of 12 `perception_confidence_drop`
scenarios are still classified as `perception_miss`. This is why root-module accuracy is high while fault Macro-F1
remains much lower than Multi-Agent + Tools.
