# Failure Sample Contract v1

`failure_sample_v1` is the machine-readable contract for safety-critical abnormal samples and diagnosis errors.
The Pydantic source of truth is `FailureSampleRecord`; its exported JSON Schema is
`docs/contracts/failure_sample_v1.schema.json`.

## Meaning And Selection

A failure sample is a scenario whose oracle fault is not `normal`, or whose diagnosis fault/root is wrong. It is
therefore broader than a diagnosis mistake:

- `is_correct=true`: a correctly diagnosed abnormal driving sample, retained for safety regression.
- `is_correct=false`: a diagnosis error, retained for error analysis and method regression.
- `tags` contains `eval_status:correct` or `eval_status:error` for filtering.

Only the evaluation/output stage may build this package. The `true_*` fields and regression expectation contain
oracle data and must never be passed back to an Agent, baseline, prompt, or diagnosis API.

## Required Fields

| Field | Contract |
| --- | --- |
| `schema_version` | Always `failure_sample_v1`. Breaking changes require a new version. |
| `package_kind` | Always `diagnosis_failure_sample`. |
| `oracle_visibility` | Always `evaluation_only`. |
| `scenario_id`, `source` | Stable sample identity and raw-data provenance. |
| `diagnosis_method` | Method that produced the prediction. |
| `predicted_*`, `true_*` | Prediction/oracle comparison. `true_*` is evaluation-only. |
| `is_correct`, `confidence` | Exact fault-and-root correctness and diagnosis confidence. |
| `evidence` | Selected typed evidence with unique `evidence_id` values. |
| `wrong_reasoning`, `correct_reasoning` | Review text; these are not hidden chain-of-thought traces. |
| `tags` | Unique `key:value` curation tags. |
| `recommended_data` | Follow-up artifacts with `high/medium/low` priority. |
| `regression_test_config` | Observed-only replay selector, expected oracle and time tolerance. |
| `scenario_record_hash` | SHA-256 of the canonical `observed_view()` only. |

## Package Layout

```text
runs/{run_id}/
  failure_samples.jsonl
  tables/failure_samples.csv
  failure_samples/{scenario_id}/failure_sample.json
```

The JSONL and per-scenario JSON contain the same typed records. CSV is an index, not the source of truth.

## Validation Rules

1. The regression selector `scenario_id` must match the package `scenario_id`.
2. `diagnosis_input` must be `observed_view_only`.
3. Evidence IDs and tags must be unique within one record.
4. `scenario_record_hash` must be a 64-character lowercase SHA-256 value.
5. Unknown fields are rejected. Consumers must branch on `schema_version` instead of guessing.

Export the current schemas with:

```bash
conda run -n yolo python scripts/export_output_schemas.py
```
