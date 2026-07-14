#!/usr/bin/env python3
import argparse
import json
from zhijia_guardian.adapters.openpilot_adapter import load_openpilot_log, summarize_log_metadata

parser = argparse.ArgumentParser()
parser.add_argument("log")
parser.add_argument("--openpilot-root")
args = parser.parse_args()
case = load_openpilot_log(args.log, openpilot_root=args.openpilot_root)
print(json.dumps(summarize_log_metadata(case), indent=2))
