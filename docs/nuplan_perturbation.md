# nuPlan Planning Perturbation

## Purpose

nuPlan provides real scene geometry, ego states, tracked objects, maps, and expert future motion, but it does not
provide a faulty tested planner output or root-cause oracle. This benchmark adds an auditable synthetic planner
perturbation while preserving the real scene skeleton.

## Generation

```bash
python scripts/generate_nuplan_perturbation.py --pairs 5 --seed 42 --clean
```

For each selected parent scene, the generator emits two opaque records:

1. A benign 0.05 m maximum lateral perturbation.
2. A local trajectory interception of a real annotated actor future position.

Both records use `trajectory_source=perturbed_planner`. The generation procedure, parent pairing, target actor,
and oracle are hidden from `observed_view()`.

## Validation

Generation rejects candidates unless:

- The benign trajectory has zero planned rectangle collisions.
- The injected trajectory has at least one planned rectangle collision.
- The target displacement is at most 8 m.

The v0.1 dataset contains five pairs. Both deterministic methods reach 10/10 fault and root accuracy, while
Multi-Agent localizes the injected frame exactly and Rule-only has 0.1999 s time MAE.

Outputs:

```text
/data5/lzx_data/Zhijia-Guardian/outputs/runs/nuplan_perturbation_v0_1_rule_seed42/
/data5/lzx_data/Zhijia-Guardian/outputs/runs/nuplan_perturbation_v0_1_multi_agent_seed42/
/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/nuplan_perturbation_v0_1_seed42/
```

The 100% classification result is an integration check, not a strong benchmark result. Future versions need
near-miss, comfort-only, lane-boundary, and variable-severity perturbations.
