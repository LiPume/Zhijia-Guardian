# Openpilot Message-Chain Recalibration TODO

Status date: 2026-07-14

- [x] Preserve the legacy implementation on `legacy-before-openpilot-recalibration`.
- [x] Audit the existing code, documents, tests, Git state, and reproducibility risks.
- [x] Remove legacy CARLA/nuScenes/nuPlan-first workflow code and stale generated demos.
- [x] Define Pydantic `DiagnosticCase`, evidence, finding, and tool-result contracts.
- [x] Add independent openpilot rlog/qlog adapter and minimal synthetic openpilot-like adapter.
- [x] Implement deterministic message-flow, CAN, control-link, safety, and evidence tools.
- [x] Implement stateful tool-use multi-agent workflow with bounded routing and trace output.
- [x] Add reproducible CLI, data-root configuration, minimal-data fetch/inspection scripts, and output packaging.
- [x] Clone openpilot shallowly under the external data root and validate a real-log smoke path.
- [x] Run the perturbed-case demo and test suite; record limitations honestly.
- [x] Rewrite project documentation, including data boundaries and legacy recalibration rationale.
- [ ] Commit checkpoints, inspect tracked files, and push `main` normally to GitHub.
