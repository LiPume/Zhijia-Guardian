#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

from zhijia_guardian.adapters import NuScenesVisionAdapter
from zhijia_guardian.agents.visual_review_agent import (
    create_visual_review_client,
    load_visual_review_config,
    run_visual_review_agent,
    select_visual_frames,
)
from zhijia_guardian.schemas.visual_review import VisualSampleFrame
from zhijia_guardian.tools.run_metrics import run_all_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Qwen visual review on raw nuScenes camera clips.")
    parser.add_argument(
        "--clip-root",
        default="/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1/raw/clips",
    )
    parser.add_argument("--run-id", default="nuscenes_real_qwen37_direct_v0_1")
    parser.add_argument("--output-root", default="/data5/lzx_data/Zhijia-Guardian/outputs/runs")
    parser.add_argument("--config", default="configs/vlm_qwen.yaml")
    parser.add_argument("--mode", choices=["direct_vlm", "vlm_with_tools"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--enable-vlm", action="store_true", help="Acknowledge that the run calls a paid API.")
    parser.add_argument("--prepare-only", action="store_true", help="Write sampled-frame manifests without API calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit <= 0:
        raise ValueError("limit must be positive")
    config = load_visual_review_config(
        args.config,
        enabled_override=True if args.enable_vlm else None,
        mode_override=args.mode,
    )
    if not args.prepare_only and not args.enable_vlm:
        raise RuntimeError("Pass --enable-vlm for API execution, or --prepare-only for an offline check.")
    adapter = NuScenesVisionAdapter(args.clip_root)
    scenario_ids = adapter.list_scenarios()
    if args.limit is not None:
        scenario_ids = scenario_ids[: args.limit]
    run_dir = Path(args.output_root) / args.run_id
    review_dir = run_dir / ("visual_inputs" if args.prepare_only else "visual_reviews")
    review_dir.mkdir(parents=True, exist_ok=True)
    client = None if args.prepare_only else create_visual_review_client(config)
    predictions = []
    for scenario_id in scenario_ids:
        clip = adapter.load_clip(scenario_id)
        scenario = adapter.load_scenario(scenario_id)
        metrics = run_all_metrics(scenario)
        if args.prepare_only:
            payload = _prepare_manifest(clip, metrics, config)
        else:
            record = run_visual_review_agent(clip, metrics, config, client)  # type: ignore[arg-type]
            payload = record.model_dump(mode="json", exclude_none=True)
            predictions.append(record.output.suspected_fault_type)
        _write_json(payload, review_dir / f"{scenario_id}.json")

    summary = {
        "task": "visual_review_prepare" if args.prepare_only else "visual_review",
        "mode": config.mode,
        "provider": config.provider,
        "model": config.model,
        "num_scenarios": len(scenario_ids),
        "api_called": not args.prepare_only,
        "prediction_counts": dict(Counter(predictions)),
        "oracle_used": False,
        "annotation_images_used": False,
        "accuracy_metrics_available": False,
    }
    run_meta = {
        **summary,
        "run_id": args.run_id,
        "clip_root": str(Path(args.clip_root).resolve()),
        "git_commit": _git_commit(),
        "created_at": datetime.now().astimezone().isoformat(),
        "config": config.public_metadata(),
    }
    _write_json(summary, run_dir / "summary.json")
    _write_json(run_meta, run_dir / "run_meta.json")
    print(f"Run complete: {run_dir}")


def _prepare_manifest(clip, metrics, config) -> dict:
    selected = select_visual_frames(clip, config.max_frames)
    sampled = [
        VisualSampleFrame(
            frame_index=index,
            timestamp=clip.frames[index].timestamp,
            image_path=clip.frames[index].image_path,
            image_sha256=hashlib.sha256(Path(clip.frames[index].image_path).read_bytes()).hexdigest(),
        ).model_dump(mode="json")
        for index in selected
    ]
    payload = {
        "schema_version": "visual_review_input_v1",
        "scenario_id": clip.scenario_id,
        "mode": config.mode,
        "sampled_frames": sampled,
        "oracle_used": False,
        "annotation_images_used": False,
    }
    if config.mode == "vlm_with_tools":
        payload["evidence_ids"] = [item.evidence_id for item in metrics.evidence]
    return payload


def _write_json(data, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
