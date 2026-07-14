# Limitations

- A rlog/qlog is an observation boundary: absent topics and decimated qlogs create `insufficient_observability`.
- A timing gap can support a suspected producer/consumer link but cannot prove why a process, network, vehicle interface, or safety layer behaved that way.
- CAN address decoding is intentionally generic; platform DBC semantics are outside this MVP.
- The offline deterministic mode demonstrates tool-use orchestration, not a claim that online LLM reasoning adds accuracy.
- Synthetic injection validates workflow mechanics only; it is not a real vehicle fault result.
- A successful synthetic repair/replay validates an injected fault mechanism only. It cannot elevate an openpilot real-log suspected link into a proven root cause.
- nuScenes and nuPlan adapters are intentionally auxiliary evidence contracts until an explicitly aligned dataset and provenance protocol are supplied.
