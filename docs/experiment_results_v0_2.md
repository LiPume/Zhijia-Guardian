# Experiment Results v0.2

## Change From v0.1

v0.2 replaces circular ego/actor collision envelopes with oriented rectangles using canonical vehicle length,
width, and yaw. It also reports fault-time coverage and conditional MAE so missing timestamps cannot improve the
localization score silently.

## Setup

- Dataset: the same 72 noisy manual canonical scenarios used by v0.1.
- Seed: 42.
- Git commit: `48f0578` for all three runs.
- Single-LLM: DeepSeek V4 Pro, temperature 0, Chat Completions JSON Output.
- Scenario ID sets: identical across all methods.

## Main Results

| Rank | Method | Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE @ Correct | Evidence Correctness | Hallucination Rate |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Multi-Agent + Tools | 0.9028 | 0.9049 | 0.9028 | 0.9833 | 0.4545 | 1.0000 | 0.0000 |
| 2 | Rule-only | 0.7361 | 0.7563 | 0.7361 | 0.9667 | 0.3956 | 1.0000 | 0.0000 |
| 3 | Single-LLM / DeepSeek V4 Pro | 0.7500 | 0.6169 | 0.9028 | 0.8667 | 0.2645 | 0.6827 | 0.1331 |

Machine-readable outputs:

```text
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/manual_v0_2_seed42/
```

## Planning-Agent Regression

Compared with v0.1, Multi-Agent + Tools changes five predictions. Three become correct and none of the old correct
predictions regress. Accuracy improves from 0.8611 to 0.9028 and Macro-F1 from 0.8606 to 0.9049.

The corrected cases include a delayed-control scenario whose planner produced a safe adjacent-lane offset and a
normal boundary scenario. Their planned paths now have positive rectangle clearance instead of false circular
overlap.

## Time-Metric Interpretation

Multi-Agent predicts a time for 98.33% of fault scenarios and for all correctly classified fault scenarios. Its
conditional MAE is higher than Rule-only because it correctly classifies additional difficult cases; MAE must be
read together with coverage and fault accuracy.

Single-LLM has the lowest conditional MAE but only 86.67% overall time coverage and 82.61% coverage among its
correct fault predictions. It must not be ranked as the best time localizer from MAE alone.

## Remaining Errors

- Multi-Agent: one control delay becomes normal; three normal boundary cases become control delay; one confidence
  drop becomes control delay; two planning risks are assigned to downstream/other modules.
- Single-LLM: 11/12 confidence drops become perception misses, despite 11/12 control delays now being correct.
- Deterministic methods retain perfect evidence correctness by construction; this validates the evidence contract,
  not open-domain reasoning ability.

## Validity Limits

The benchmark remains synthetic and uses one seed. The next external-validity step is nuPlan real-scene trajectory
perturbation, followed by CARLA fault injection and held-out multi-seed evaluation.
