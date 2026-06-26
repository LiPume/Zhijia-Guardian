from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from zhijia_guardian.workbench import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    list_runs,
    load_diagnosis,
    load_metrics,
    load_run,
    read_report,
    resolve_figure,
)


st.set_page_config(page_title="Zhijia Guardian", page_icon=None, layout="wide")
LOCAL_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+\.svg)\)")


def main() -> None:
    _inject_style()
    st.title("智驾卫士")

    output_root = Path(
        st.sidebar.text_input(
            "Output Root",
            value=str(DEFAULT_OUTPUT_ROOT),
        )
    )
    run_paths = list_runs(output_root)
    if not run_paths:
        st.error(f"No experiment runs found under {output_root}")
        return

    run_names = [path.name for path in run_paths]
    selected_run = st.sidebar.selectbox("Run", run_names, index=0)
    run_dir = run_paths[run_names.index(selected_run)]
    bundle = _load_run_cached(str(run_dir))

    st.sidebar.caption(f"method: {bundle.method}")
    st.sidebar.caption(f"scenarios: {len(bundle.scenarios)}")

    filters = _sidebar_filters(bundle.eval_rows)
    filtered_rows = _filter_rows(bundle.eval_rows, filters)
    scenario_id = _scenario_selector(filtered_rows, bundle.scenarios)

    tab_run, tab_cases, tab_diagnosis, tab_artifacts = st.tabs(["Run", "Cases", "Diagnosis", "Artifacts"])
    with tab_run:
        _render_run_tab(bundle)
    with tab_cases:
        _render_cases_tab(filtered_rows, bundle.error_rows)
    with tab_diagnosis:
        _render_diagnosis_tab(bundle.run_dir, scenario_id)
    with tab_artifacts:
        _render_artifacts_tab(bundle)


@st.cache_data(show_spinner=False)
def _load_run_cached(run_dir: str):
    return load_run(run_dir)


@st.cache_data(show_spinner=False)
def _load_diagnosis_cached(run_dir: str, scenario_id: str):
    return load_diagnosis(run_dir, scenario_id)


@st.cache_data(show_spinner=False)
def _load_metrics_cached(run_dir: str, scenario_id: str):
    return load_metrics(run_dir, scenario_id)


def _sidebar_filters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pred_labels = sorted({str(row.get("pred_fault_type")) for row in rows if row.get("pred_fault_type")})
    true_labels = sorted({str(row.get("true_fault_type")) for row in rows if row.get("true_fault_type")})
    st.sidebar.divider()
    correctness = st.sidebar.radio("Cases", ["all", "errors", "correct"], horizontal=True)
    true_filter = st.sidebar.multiselect("True Fault", true_labels)
    pred_filter = st.sidebar.multiselect("Pred Fault", pred_labels)
    return {"correctness": correctness, "true": set(true_filter), "pred": set(pred_filter)}


def _filter_rows(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    filtered = []
    for row in rows:
        if filters["correctness"] == "errors" and row.get("fault_correct") is True and row.get("root_correct") is True:
            continue
        if filters["correctness"] == "correct" and not (row.get("fault_correct") is True and row.get("root_correct") is True):
            continue
        if filters["true"] and row.get("true_fault_type") not in filters["true"]:
            continue
        if filters["pred"] and row.get("pred_fault_type") not in filters["pred"]:
            continue
        filtered.append(row)
    return filtered


def _scenario_selector(rows: list[dict[str, Any]], fallback: list[str]) -> str:
    candidates = [str(row["scenario_id"]) for row in rows if row.get("scenario_id")] or fallback
    return st.sidebar.selectbox("Scenario", candidates, index=0)


def _render_run_tab(bundle) -> None:
    summary = bundle.summary
    cols = st.columns(6)
    metric_items = [
        ("Scenarios", summary.get("num_scenarios")),
        ("Fault Acc", summary.get("fault_accuracy")),
        ("Macro-F1", summary.get("fault_macro_f1")),
        ("Root Top-1", summary.get("root_top1_accuracy")),
        ("Time MAE", summary.get("fault_start_time_mae")),
        ("Hallucination", summary.get("hallucination_rate")),
    ]
    for col, (label, value) in zip(cols, metric_items):
        col.metric(label, _fmt(value))

    left, right = st.columns([1.05, 1.0], gap="large")
    with left:
        confusion_path = resolve_figure(bundle.run_dir)
        if confusion_path.exists():
            st.image(str(confusion_path), use_container_width=True)
    with right:
        st.subheader("Leaderboard")
        leaderboard = bundle.run_dir / "tables" / "leaderboard.csv"
        if leaderboard.exists():
            st.dataframe(pd.read_csv(leaderboard), use_container_width=True, hide_index=True)
        st.subheader("Run Meta")
        st.json(bundle.run_meta, expanded=False)

    st.subheader("Run Report")
    st.markdown(_safe_markdown(read_report(bundle.run_dir)))


def _render_cases_tab(rows: list[dict[str, Any]], error_rows: list[dict[str, Any]]) -> None:
    left, right = st.columns([1.2, 1.0], gap="large")
    with left:
        st.subheader("Filtered Cases")
        st.dataframe(_case_frame(rows), use_container_width=True, hide_index=True)
    with right:
        st.subheader("Error Cases")
        st.dataframe(_case_frame(error_rows), use_container_width=True, hide_index=True)


def _render_diagnosis_tab(run_dir: Path, scenario_id: str) -> None:
    diagnosis = _load_diagnosis_cached(str(run_dir), scenario_id)
    metrics = _load_metrics_cached(str(run_dir), scenario_id)

    cols = st.columns(5)
    cols[0].metric("Scenario", scenario_id)
    cols[1].metric("Fault", diagnosis.get("predicted_fault_type"))
    cols[2].metric("Root", diagnosis.get("predicted_root_module"))
    cols[3].metric("Start", _fmt(diagnosis.get("predicted_fault_start_time")))
    cols[4].metric("Confidence", _fmt(diagnosis.get("confidence")))

    fig_left, fig_right = st.columns(2, gap="large")
    bev = resolve_figure(run_dir, scenario_id, "bev")
    timeline = resolve_figure(run_dir, scenario_id, "timeline")
    with fig_left:
        if bev.exists():
            st.image(str(bev), use_container_width=True)
    with fig_right:
        if timeline.exists():
            st.image(str(timeline), use_container_width=True)

    root_col, trace_col = st.columns([1.0, 1.25], gap="large")
    with root_col:
        st.subheader("Candidate Root Causes")
        st.dataframe(_candidate_frame(diagnosis), use_container_width=True, hide_index=True)
        st.subheader("Claims")
        st.dataframe(_claims_frame(diagnosis), use_container_width=True, hide_index=True)
    with trace_col:
        st.subheader("Agent Trace")
        st.dataframe(_trace_frame(diagnosis), use_container_width=True, hide_index=True)
        st.subheader("Evidence")
        st.dataframe(_evidence_frame(metrics, diagnosis), use_container_width=True, hide_index=True)

    with st.expander("Markdown Report", expanded=False):
        st.markdown(_safe_markdown(read_report(run_dir, scenario_id)))


def _render_artifacts_tab(bundle) -> None:
    st.subheader("Output Package")
    files = []
    for path in sorted(bundle.run_dir.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "file": str(path.relative_to(bundle.run_dir)),
                    "size_kb": round(path.stat().st_size / 1024, 2),
                }
            )
    st.dataframe(pd.DataFrame(files), use_container_width=True, hide_index=True)

    st.subheader("Manifest")
    st.json(bundle.manifest, expanded=True)


def _case_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    cols = [
        "scenario_id",
        "true_fault_type",
        "pred_fault_type",
        "true_root_module",
        "pred_root_module",
        "time_abs_error",
        "fault_correct",
        "root_correct",
    ]
    return pd.DataFrame([{key: row.get(key) for key in cols} for row in rows])


def _candidate_frame(diagnosis: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rank": index,
                "fault_type": item.get("fault_type"),
                "root_module": item.get("root_module"),
                "score": item.get("score"),
                "confidence": item.get("confidence"),
                "evidence_ids": ", ".join(item.get("evidence_ids", [])),
            }
            for index, item in enumerate(diagnosis.get("candidate_root_causes", []), start=1)
        ]
    )


def _trace_frame(diagnosis: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "agent": item.get("agent_name"),
                "status": item.get("status"),
                "summary": item.get("summary"),
                "evidence_ids": ", ".join(item.get("evidence_ids", [])),
            }
            for item in diagnosis.get("agent_trace", [])
        ]
    )


def _claims_frame(diagnosis: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "claim_id": item.get("claim_id"),
                "claim": item.get("claim"),
                "fault_type": item.get("predicted_fault_type"),
                "root_module": item.get("predicted_root_module"),
                "evidence_ids": ", ".join(item.get("evidence_ids", [])),
            }
            for item in diagnosis.get("claims", [])
        ]
    )


def _evidence_frame(metrics: dict[str, Any], diagnosis: dict[str, Any]) -> pd.DataFrame:
    evidence = diagnosis.get("evidence") or metrics.get("evidence") or []
    return pd.DataFrame(
        [
            {
                "evidence_id": item.get("evidence_id"),
                "metric": item.get("metric_name"),
                "status": item.get("status"),
                "time": item.get("time"),
                "value": item.get("value"),
                "supports": ", ".join(item.get("supports", [])),
                "contradicts": ", ".join(item.get("contradicts", [])),
                "description": item.get("description"),
            }
            for item in evidence
        ]
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _safe_markdown(text: str) -> str:
    return LOCAL_IMAGE_PATTERN.sub(lambda match: f"**{match.group(1) or 'figure'}:** `{match.group(2)}`", text)


def _inject_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
        h1 {font-size: 1.55rem; margin-bottom: 0.4rem;}
        h2, h3 {font-size: 1.05rem; margin-top: 0.9rem;}
        [data-testid="stMetric"] {
            background: #fbfbf8;
            border: 1px solid #d7d7cf;
            padding: 0.75rem 0.8rem;
        }
        [data-testid="stSidebar"] {
            background: #f4f5f2;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
