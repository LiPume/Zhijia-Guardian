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
| `confusion_matrix.json` | Sparse confusion matrix counts. |
| `run_meta.json` | Reproducibility metadata: method, dataset, seed, configs, git commit. |

## Directories

| Directory | Contents |
| --- | --- |
| `metrics/` | Per-scenario metric and evidence JSON. |
| `diagnoses/` | Per-scenario structured diagnosis JSON. |
| `reports/` | Per-scenario Markdown reports with figure links. |
| `figures/` | Per-scenario BEV/timeline SVGs and run-level confusion matrix SVG. |
| `tables/` | Derived tables such as `errors.csv` and `leaderboard.csv`. |

## Scenario Report

Each `reports/{scenario_id}.md` contains:

- Summary prediction.
- BEV and evidence timeline figures.
- Candidate root causes.
- Agent trace.
- Claims with `evidence_ids`.
- Evidence list.

Every claim must reference valid evidence IDs. Diagnosis agents and reports must not read `oracle` or `source.generation`.

## Run Report

`run_report.md` is the first file to open for demos and reviews. It contains:

- Method and dataset metadata.
- Aggregate metrics.
- Confusion matrix figure.
- Error-case table with links to scenario reports.
- Sparse confusion counts.
