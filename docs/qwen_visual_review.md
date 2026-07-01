# Qwen Visual Review

## Decision

Qwen3.7-Plus can inspect the camera frames directly. It does not need another LLM Agent to unlock vision. The
project wraps the API as an optional Visual Review Agent for deterministic sampling, data-boundary enforcement,
structured output validation, cost opt-in, retries, and audit metadata.

The visual result remains a sidecar in v0.1. It does not vote in deterministic root-cause ranking until a labeled
visual benchmark shows that it improves accuracy without increasing hallucination.

## Two Experiment Modes

| Mode | Model input | Purpose |
| --- | --- | --- |
| `direct_vlm` | Eight uniformly sampled raw frames and timestamps | Test whether one multimodal model can diagnose by looking directly. |
| `vlm_with_tools` | The same raw frames plus sanitized metric values/evidence IDs | Test whether tools improve grounding and report usefulness. |

Neither mode receives projected annotation overlays, `actors_gt`, oracle labels, fault-bearing paths, or the
deterministic Agent prediction. The original images under nuScenes `samples/CAM_FRONT/` are encoded as Base64 data
URLs. Output must validate against `visual_review_v1`.

## Configuration

Add these variables to the local `.env` without committing them:

```bash
DASHSCOPE_API_KEY=sk-...
# Optional regional/workspace endpoint override:
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

The default model and limits are in `configs/vlm_qwen.yaml`. API calls remain disabled by default.

## Offline Preparation

This verifies frame selection and hashes without making a paid request:

```bash
conda run -n yolo python experiments/run_visual_review.py \
  --prepare-only \
  --mode direct_vlm \
  --run-id nuscenes_real_qwen37_direct_v0_1_prepare
```

The five real clips have already produced prepare-only manifests under
`/data5/lzx_data/Zhijia-Guardian/outputs/runs/`. Each scenario selects eight frames and records
`oracle_used=false`, `annotation_images_used=false`, and the SHA-256 hash of every image.

## API Smoke Runs

Run one clip first:

```bash
conda run -n yolo python experiments/run_visual_review.py \
  --enable-vlm --limit 1 \
  --mode direct_vlm \
  --run-id nuscenes_real_qwen37_direct_v0_1

conda run -n yolo python experiments/run_visual_review.py \
  --enable-vlm --limit 1 \
  --mode vlm_with_tools \
  --run-id nuscenes_real_qwen37_tools_v0_1
```

Only after checking JSON validity, token usage, latency, and visual claims should all five clips be sent. These runs
still cannot report fault Accuracy/F1 because nuScenes has no fault/root oracle.

## What The VLM Can And Cannot Do

Useful visual tasks:

- describe weather, illumination, occlusion, road layout, and dense interactions;
- flag visible road users that deserve detector review;
- explain why a tiny or occluded object may be difficult;
- produce an engineer-readable visual summary across sampled frames.

Unsupported conclusions from pixels alone:

- precise TTC, metric distance, or actuator delay;
- planner trajectory correctness;
- internal perception root cause;
- legal responsibility or definitive fault labels.
