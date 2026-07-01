# nuScenes Real CAM_FRONT + YOLO v0.1

## Purpose

This module verifies that real camera frames and frozen detector outputs can enter the same Canonical Scenario and
multi-Agent diagnosis path. It is an unlabeled field-data diagnosis run, not a fault-classification benchmark.

## Data And Model

- Source: nuScenes mini v1.0 real driving data.
- Scenes: `scene-0103`, `scene-0655`, `scene-0553`, `scene-0796`, `scene-1094`.
- Input: 202 `CAM_FRONT` key frames, 1600x900, approximately 2 Hz.
- Detector: official Ultralytics 8.3.215 with frozen `yolov8n.pt`, confidence threshold 0.25.
- Classes: person, bicycle, car, motorcycle, bus, and truck.
- Fault/root oracle: unavailable.

The original 3D nuScenes annotations are projected into the front camera with `ego_pose`,
`calibrated_sensor.camera_intrinsic`, and quaternion transforms. YOLO 2D boxes are associated to projected boxes by
one-to-one IoU matching at 0.3. YOLO determines class, box, and confidence; annotation association supplies the
offline match identity and world position. Unmatched 2D boxes keep `x/y=null` rather than receiving fake depth.

## Reproduction

Only the 71 MB front-camera key-frame subset needs to be extracted from the existing archive:

```bash
tar -xzf /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/raw/v1.0-mini.tgz \
  -C /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted \
  --wildcards 'samples/CAM_FRONT/*'

conda run -n yolo python scripts/run_nuscenes_yolo_benchmark.py --clean

conda run -n yolo python experiments/run_diagnosis.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1/canonical/scenarios.jsonl \
  --run-id nuscenes_real_yolo_v0_1_multi_agent \
  --method multi_agent_tools
```

The `yolo` environment must use the official Ultralytics package rather than a locally modified editable fork. No
new Torch installation is required.

## Detector Results

| Metric | Result |
| --- | ---: |
| Visible projected annotations | 2395 |
| Key actor frame instances | 1549 |
| YOLO detections | 1555 |
| Matched detections | 1127 |
| Annotation recall | 0.4706 |
| Key actor recall | 0.5391 |
| Detection precision | 0.7248 |
| Matched class accuracy | 0.9290 |

Counts are frame-level instances, not unique physical actors. The lightweight COCO detector has strong class
agreement on matched objects, but misses many small, distant, occluded, or crowded road users. `scene-0553` has the
best key-actor recall at 0.7366; dense `scene-1094` reaches only 0.3463.

## Diagnosis Result

All five clips produce `perception_miss` as the leading engineering hypothesis. Planning and Control Agents are
explicitly `skipped` because nuScenes does not contain planner output or control commands. No Accuracy, Macro-F1,
Root Top-1, or failure-sample package is generated because no fault/root oracle exists.

The first real run exposed a false diagnosis pattern: natural scale and visibility changes made all clips look like
confidence-drop faults. The confidence tool now requires two persistent low-confidence frames, a still-key actor,
and comparable image-box area. Miss evidence wins when persistent misses and confidence variation coexist. Manual
v0.3, CARLA weather, and CARLA closed-loop retained 1.0000 Multi-Agent Macro-F1 after this correction.

## Outputs

```text
/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1/
  manifest.json
  raw/clips/*.json
  canonical/scenarios.jsonl
  media/frames/
  media/videos/

/data5/lzx_data/Zhijia-Guardian/outputs/runs/nuscenes_real_yolo_v0_1_multi_agent/
  run_report.md
  metrics/
  diagnoses/
  reports/
  figures/
```

Two H.264 review videos are committed under `demo/real_nuscenes/`. Green GT boxes are correctly associated, red GT
boxes are unmatched, blue YOLO boxes are associated, and yellow YOLO boxes are unmatched.

## Limitations

1. Only the front camera is used; LiDAR, radar, side/rear cameras, and map context are absent.
2. Projected dataset annotation is an offline benchmark aid and is not available on a production vehicle.
3. The diagnosis reports perception anomalies, not why the base detector internally failed.
4. The five clips are a real-data compatibility and failure-discovery sample, not a population estimate.
5. Fault diagnosis accuracy still requires controlled CARLA/manual oracle datasets or expert-labeled vehicle logs.
