# Diagnosis Report Contract v1

Every scenario has two paired outputs:

- `diagnoses/{scenario_id}.json`: machine-readable `diagnosis_v1`, the source of truth.
- `reports/{scenario_id}.md`: human-readable `diagnosis_report_v1`, a deterministic view of the JSON.

The JSON Schema is `docs/contracts/diagnosis_v1.schema.json`. Markdown parsers should identify sections by
heading, not by line number.

## Fixed Section Order

1. `Metadata`
2. `Diagnosis Summary`
3. `Figures`
4. `Candidate Root Causes`
5. `Evidence Chain`
6. `Claims`
7. `Agent Execution Trace`
8. `Uncertainty And Limitations`
9. `Recommended Actions`

All sections must exist even when their content is unavailable. Missing content is written explicitly instead of
silently removing a section.

## Evidence Rules

1. Every claim has a unique `claim_id` and one or more valid `evidence_ids`, except an explicitly uncertain claim.
2. Every candidate root cause cites evidence IDs present in the diagnosis evidence array.
3. Evidence records contain `metric_name`, `status`, value/threshold/time, `supports`, and `contradicts`.
4. Recommendations are selected from the predicted root module and are not treated as diagnosis evidence.
5. The report never contains oracle labels or generation metadata.

## Stability And Safety

- `diagnosis_v1` and `diagnosis_report_v1` are independent versions because presentation can evolve without
  changing the machine record.
- The deterministic Markdown template is the default product output. Optional LLM wording must preserve all
  cited IDs and pass the same evidence validation before display.
- The report is an offline engineering hypothesis, not a safety certification or legal-liability conclusion.
