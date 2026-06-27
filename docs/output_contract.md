# Output Contract

Each experiment writes a reproducible run package under:

```text
/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/
```

## Top-Level Files

| File | Purpose |
| --- | --- |
| `run_report.md` | Human-readable run summary with metrics, confusion matrix, and error cases. |
| `artifacts_manifest.json` | Machine-readable pointers to key output files. |
| `summary.json` | Aggregate metrics for the run. |
| `eval.csv` | Per-scenario evaluation rows. |
| `failure_samples.jsonl` | Consolidated failure samples for later data curation or SFT/DPO preparation. |
| `confusion_matrix.json` | Sparse confusion matrix counts. |
| `run_meta.json` | Reproducibility metadata: method, dataset, seed, configs, git commit. |

For `single_llm` runs, `run_meta.json` also records non-secret LLM settings. Per-scenario agent traces may record
response IDs and token usage. API keys and base URLs are never written to output artifacts.
With `--resume`, existing per-scenario metrics and diagnoses are validated and reused before missing scenarios run.

## Cross-Run Comparison

`experiments/compare_runs.py` validates that all input runs contain the same scenario IDs, ranks methods by fault
Macro-F1, and writes `comparison.csv`, `comparison.json`, and `comparison.md` under an explicit comparison output
directory. The v0.1 package is stored at
`/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/manual_v0_1_seed42/`.

## Directories

| Directory | Contents |
| --- | --- |
| `metrics/` | Per-scenario metric series and evidence JSON. |
| `diagnoses/` | Per-scenario structured diagnosis JSON. |
| `reports/` | Per-scenario Markdown reports with figure links. |
| `figures/` | Per-scenario BEV/timeline SVGs and run-level confusion matrix SVG. |
| `tables/` | Derived tables such as `errors.csv` and `leaderboard.csv`. |
| `failure_samples/` | Per-scenario packages: `failure_samples/{scenario_id}/failure_sample.json`. |

## Scenario Report

Each `reports/{scenario_id}.md` contains:

- Summary prediction.
- BEV and evidence timeline figures.
- Candidate root causes.
- Agent trace.
- Claims with `evidence_ids`.
- Evidence list.

Every claim must reference valid evidence IDs. Diagnosis agents and reports must not read `oracle` or `source.generation`.

## Metrics JSON

Each `metrics/{scenario_id}.json` may contain:

- `series`: time-series metrics such as `ego_speed`, `ego_longitudinal_acceleration`, `ego_jerk`, and `ego_yaw_rate`.
- `evidence`: thresholded metric findings with unique `evidence_id`.

Comfort evidence is auxiliary. It is shown for review and timeline context, but it does not directly support a
fault label in the first rule-based MVP.

## Fault-Time Metrics

Run summaries report both localization error and prediction coverage:

- `fault_start_time_mae`: legacy MAE over fault scenarios with any predicted time, including wrong fault labels.
- `fault_start_time_coverage`: fraction of oracle fault scenarios with a predicted time.
- `fault_start_time_mae_at_correct_fault`: MAE restricted to correctly classified fault scenarios.
- `fault_start_time_coverage_at_correct_fault`: time coverage among correctly classified fault scenarios.

The conditional MAE must be read together with its coverage; a method cannot improve by omitting difficult times.

## Run Report

`run_report.md` is the first file to open for demos and reviews. It contains:

- Method and dataset metadata.
- Aggregate metrics.
- Confusion matrix figure.
- Failure sample count and links to the JSONL/table/package directory.
- Error-case table with links to scenario reports.
- Sparse confusion counts.

## Failure Sample Package

Failure samples are written only by the evaluation/output stage. They may contain oracle-derived `true_*`
fields, so diagnosis agents and baselines must never read them.

Each `failure_samples/{scenario_id}/failure_sample.json` contains:

- `scenario_id`, predicted fault/root/start time, true fault/root/start time, and `is_correct`.
- Selected evidence records from the diagnosis output.
- `wrong_reasoning` and `correct_reasoning` for review or future preference-data curation.
- `tags` for dataset, method, fault class, root module, difficulty, and noise profile.
- `recommended_data` listing follow-up logs or clips an engineer should inspect.
- `regression_test_config` with observed-only replay input and oracle expectations.
- `scenario_record_hash`, computed from `ScenarioRecord.observed_view()` only.
