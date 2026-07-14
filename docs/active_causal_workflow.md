# Active causal workflow

The prior tool workflow is a necessary factual substrate, not the final contribution. This extension makes a bounded diagnostic decision loop:

```text
primary route observations → specialist evidence → hypothesis board
  → select highest-value feasible action
  → synthetic repair/replay or explicit observability gap
  → compare predicted and observed effect → update finding → audit
```

The counterfactual agent currently acts in a controllable synthetic ADSLogRecord sandbox; the same interface is reserved for a future CARLA backend. It receives a registered repair tool and never reads the injected-fault oracle. In a real rlog/qlog case the action is `not_feasible` (or no action is selected), and the system asks for more process/safety logs instead of modifying the real record.

`validated_root_cause` is deliberately narrow: the injected mechanism changed as predicted in that controlled replay. It is not permitted for a real openpilot route.

nuScenes and nuPlan adapters produce `AuxiliaryEvidenceBundle` records with `same_route_as_primary=false`. They can support adapter capability studies and route a perception/planning investigation, but Evidence Auditor records a source-boundary warning and blocks any claim that they completed the primary route's causal chain.
