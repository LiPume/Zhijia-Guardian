# Data sources

The project uses the current openpilot reference only under `$ZHIJIA_DATA_ROOT/reference/openpilot`, created by a depth-one, blob-filtered clone. The adapter is compatible with local `rlog.zst`, `qlog.zst`, and legacy `.bz2` logs through upstream `LogReader`.

For a minimal public smoke input, openpilot's own `tools/lib/tests/test_logreader.py` currently references a single OpenPilotCI qlog URL. `scripts/fetch_minimal_sample.py` downloads only that one file after an explicit command. On 2026-07-14 it fetched `openpilotci-2019-06-13-segment3-qlog.bz2` (239,924 bytes) and the independent adapter parsed 3,707 messages across 12 observed topics. This repo does not clone commaCarSegments, nuScenes or nuPlan, and never treats separate datasets as one physical control route.
