# nuScenes Real Six-Camera + YOLO v0.2

## Scope

This benchmark extends the real nuScenes path from one front camera to all six synchronized camera channels. It
uses two real scenes, 12 scene-camera clips, and 486 key frames. Each camera clip is converted independently to a
Canonical `ScenarioRecord`; this prevents duplicate views of the same actor from being counted as false positives.

The benchmark is six-camera 2D inference, not camera fusion and not a LiDAR/3D detector. nuScenes annotations are
used only for offline projection and association. No fault/root oracle is created.

## Reproduction

Extract the five additional camera directories from the existing complete mini archive:

```bash
tar -xzf /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/raw/v1.0-mini.tgz \
  -C /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted \
  samples/CAM_FRONT_LEFT samples/CAM_FRONT_RIGHT \
  samples/CAM_BACK_LEFT samples/CAM_BACK samples/CAM_BACK_RIGHT

conda run -n yolo python scripts/run_nuscenes_multicamera_benchmark.py --clean

conda run -n yolo python experiments/run_diagnosis.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_multicam_v0_2/canonical/scenarios.jsonl \
  --run-id nuscenes_real_multicam_v0_2_multi_agent \
  --method multi_agent_tools
```

## Detector Results

| Metric | Result |
| --- | ---: |
| Real scenes | 2 |
| Scene-camera clips | 12 |
| Frames | 486 |
| Visible projected annotation instances | 5015 |
| YOLO detections | 3387 |
| Matched detections | 2430 |
| Annotation recall | 0.4845 |
| Key-actor recall | 0.5525 |
| Detection precision | 0.7174 |
| Matched class accuracy | 0.9420 |

| Distance | Visible GT | Matched | Annotation recall | Key-actor recall |
| --- | ---: | ---: | ---: | ---: |
| 0-20 m | 1420 | 1031 | 0.7261 | 0.7261 |
| 20-40 m | 2229 | 1019 | 0.4572 | 0.4676 |
| 40 m+ | 1366 | 380 | 0.2782 | 0.4131 |

The large distance gradient is the main useful result: the same frozen lightweight detector loses substantial
recall as actors become distant. This is evidence about detector behavior, not a fault-label accuracy result.

## Diagnosis Result

All 12 clips produce `perception_miss` as the leading engineering hypothesis. Planning and Control Agents are each
skipped 12 times because nuScenes has no planner output or control command. This is a prediction distribution, not
12/12 accuracy. The unlabeled runner intentionally omits `eval.csv`, Accuracy, F1, and failure-sample packages.

## Outputs

```text
/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_multicam_v0_2/
  manifest.json
  raw/clips/*.json
  canonical/scenarios.jsonl
  media/frames/
  media/videos/*six_camera_mosaic.mp4

/data5/lzx_data/Zhijia-Guardian/outputs/runs/nuscenes_real_multicam_v0_2_multi_agent/
  summary.json
  metrics/
  diagnoses/
  reports/
  figures/

demo/real_nuscenes_multicam/
  scene-0103-six-camera-diagnosis.mp4
  scene-0655-six-camera-diagnosis.mp4
```

The committed demo videos are H.264, 1920x720, 2 fps. The top row is front-left/front/front-right and the bottom
row is back-left/back/back-right.

## Remaining Work

1. Run a frozen nuScenes-native 3D detector on LiDAR or fused camera/LiDAR input.
2. Add 3D mAP/NDS and depth-error metrics instead of inferring world position from matched annotations.
3. Add manual or expert review before comparing multimodal-model usefulness on unlabeled clips.
