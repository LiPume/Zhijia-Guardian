# Streamlit Workbench

The workbench is a read-only UI for experiment output packages. It does not run CARLA, call LLMs, or modify diagnosis results.

## Start

```bash
cd /home/lzx/Zhijia-Guardian
conda activate yolo
pip install -e ".[app]"
streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=8501
```

Default output root:

```text
/data5/lzx_data/Zhijia-Guardian/outputs/runs
```

## Views

| View | Content |
| --- | --- |
| `Run` | Aggregate metrics, leaderboard, run metadata, confusion matrix, run report. |
| `Cases` | Filtered scenario table and error-case table. |
| `Diagnosis` | BEV, evidence timeline, candidate root causes, agent trace, claims, evidence. |
| `Artifacts` | Files included in the selected output package and manifest. |

The UI reads:

- `run_report.md`
- `summary.json`
- `eval.csv`
- `tables/errors.csv`
- `tables/leaderboard.csv`
- `diagnoses/*.json`
- `metrics/*.json`
- `figures/*.svg`

## Boundary

The workbench only reads existing output artifacts. It does not read `oracle` directly and does not regenerate metrics or diagnoses.
