# CARLA Extreme Weather Benchmark v0.1

## Scope

This benchmark checks whether the existing diagnosis graph remains stable when the same fault mechanisms are
executed under held-out CARLA weather profiles. It does not claim visual detector robustness.

| Split | Weather profile | Key parameters |
| --- | --- | --- |
| train | `heavy_rain_day` | precipitation 100, wetness 100, fog 20, daytime |
| val | `dense_fog_dawn` | fog 100, distance 2 m, dawn |
| test | `night_storm` | precipitation 90, wind 100, fog 50, sun altitude -25 |

Each weather profile has four actual CARLA rollouts: normal, perception confidence drop, planning collision risk,
and control delay. Scenario IDs and paths contain no fault label. Normal runs do not collide; all three injected
fault cases collide in each weather profile.

## Data Boundary

Perception detections are generated from CARLA simulation annotations. Weather changes the CARLA environment,
but it does not degrade a real image detector. Only the `perception_confidence_drop` case changes detector output.
Therefore this benchmark validates diagnosis and causal attribution under weather context, not camera/LiDAR model
performance. A future visual-weather benchmark must record sensor media and run a frozen detector.

## Reproduction

```bash
./carla.sh /Game/Carla/Maps/Town10HD_Opt

conda run -n yolo python scripts/record_carla_weather_benchmark.py \
  --output-root /data5/lzx_data/Zhijia-Guardian/datasets/carla/extreme_weather_v0_1 \
  --seed 42 --clean
```

Canonical splits are written to `canonical/splits/{train,val,test}.jsonl`. The split unit is the complete weather
profile, so the test environment is never present in train or validation.

## Results

Full 12-scenario set and held-out four-scenario `night_storm` test produce the same result:

| Method | Fault Accuracy | Macro-F1 | Root Top-1 | Time MAE@Correct | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule-only | 0.5000 | 0.3750 | 0.5000 | 0.0000 | 1.0000 | 0.0000 |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |

Rule-only selects the downstream control delay for perception and planning cases. Multi-Agent + Tools uses the
earlier module-specific evidence to recover the injected root cause. The trajectories are deliberately controlled
and repeated across three weather settings, so this is a mechanism and environment-compatibility test, not an
estimate of natural-weather generalization.
