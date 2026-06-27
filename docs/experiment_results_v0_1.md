# Experiment Results v0.1

## Setup

- Dataset: 72 noisy manual canonical scenarios, 12 per fault class.
- Seed: 42.
- Compared scenario IDs: identical across all three runs.
- Git commit: `3691b8f` for all refreshed run metadata.
- Single-LLM: DeepSeek V4 Pro, temperature 0, Chat Completions JSON Output.
- Diagnosis inputs: observed-derived summaries and metrics only; no oracle, generation metadata, file labels, or
  metric `supports`/`contradicts` hints.

## Main Results

| Rank | Method | Accuracy | Macro-F1 | Root Top-1 | Time MAE | Evidence Correctness | Hallucination Rate |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Multi-Agent + Tools | 0.8611 | 0.8606 | 0.8611 | 0.4967 | 1.0000 | 0.0000 |
| 2 | Rule-only | 0.7361 | 0.7533 | 0.7361 | 0.6529 | 1.0000 | 0.0000 |
| 3 | Single-LLM / DeepSeek V4 Pro | 0.5694 | 0.4156 | 0.7361 | 0.3511 | 0.7286 | 0.1412 |

The machine-readable comparison package is stored at:

```text
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/manual_v0_1_seed42/
```

## Single-LLM Class Results

| True class | Support | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| normal | 12 | 1.0000 | 0.5833 | 0.7368 |
| perception_false_positive | 12 | 1.0000 | 1.0000 | 1.0000 |
| perception_miss | 12 | 0.4615 | 1.0000 | 0.6316 |
| planning_collision_risk | 12 | 0.4000 | 0.8333 | 0.5405 |
| perception_confidence_drop | 12 | 0.0000 | 0.0000 | 0.0000 |
| control_delay | 12 | 0.0000 | 0.0000 | 0.0000 |

## Interpretation

Multi-Agent + Tools performs best because its module agents check field availability, separate perception,
planning, and control evidence, and rank propagation-aware root causes. The improvement should not be attributed
to the number of agents alone.

Single-LLM evidence coverage is 1.0, but its evidence correctness is 0.7286 and hallucination rate is 0.1412.
Coverage alone is therefore insufficient: a claim can cite an existing evidence ID that does not support it.

The lower Single-LLM time MAE must not be interpreted as overall superiority. Fault-time error is available only
when the output contains a timestamp, while its fault classification accuracy is substantially lower.

## Validity Limits

- The benchmark is synthetic, although it follows the canonical real-data-compatible schema.
- Rule and agent thresholds were developed against the same scenario generator family.
- nuScenes and nuPlan are currently adapter/schema smoke tests, not root-cause benchmarks.
- CARLA/SafeBench fault injection and an untouched held-out test split are required before making a stronger
  generalization claim.
