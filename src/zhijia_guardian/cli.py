from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from zhijia_guardian.adapters import generate_clean_case, inject_perturbation, load_case_json, save_case_json
from zhijia_guardian.reporting import write_artifacts
from zhijia_guardian.workflow import run_diagnostic_workflow


def demo(config_path: str) -> int:
  config = yaml.safe_load(Path(config_path).read_text())
  root = Path(config.get("data_root") or os.environ.get("ZHIJIA_DATA_ROOT", "/data5/lzx_data/Zhijia-Guardian"))
  clean = generate_clean_case()
  injection = dict(config.get("injection", {}))
  if "type" in injection:
    injection["kind"] = injection.pop("type")
  perturbed, manifest = inject_perturbation(clean, **injection)
  save_case_json(clean, root / "synthetic" / "clean_case.json")
  save_case_json(perturbed, root / "perturbed" / "perturbed_case.json")
  (root / "perturbed" / "perturbation_manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
  diagnosis, state = run_diagnostic_workflow(perturbed, max_agent_rounds=config.get("max_agent_rounds", 3), max_tool_calls=config.get("max_tool_calls", 20))
  artifacts = write_artifacts(root / "outputs", state.case, diagnosis, state.trace)
  print(f"输入日志: synthetic clean/perturbed openpilot-like timeline")
  print(f"可用 topic: {', '.join(state.available_topics)}")
  print("是否为真实数据: False; 是否进行了扰动: True")
  print(f"调用 Agent: {', '.join(entry.agent for entry in state.trace)}")
  print(f"调用 tools: {', '.join(sorted({result.tool_name for result in state.tool_results}))}")
  print(f"最终 suspected link: {diagnosis.findings[0].suspected_link if diagnosis.findings else 'cannot_determine_root_cause'}")
  print(f"报告路径: {artifacts['report']}")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(prog="zhijia-guardian")
  sub = parser.add_subparsers(dest="command", required=True)
  command = sub.add_parser("demo")
  command.add_argument("--config", default="configs/demo.yaml")
  args = parser.parse_args()
  return demo(args.config)


if __name__ == "__main__":
  raise SystemExit(main())
