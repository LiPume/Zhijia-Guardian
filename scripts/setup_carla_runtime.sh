#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${ZHJ_DATA_ROOT:-/data5/lzx_data/Zhijia-Guardian}"
CARLA_ROOT="${CARLA_ROOT:-${DATA_ROOT}/third_party/carla/0.9.15/runtime}"
SCENARIO_RUNNER_ROOT="${SCENARIO_RUNNER_ROOT:-${DATA_ROOT}/third_party/scenario_runner/0.9.15}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -x "${CARLA_ROOT}/CarlaUE4.sh" ]]; then
  echo "CARLA runtime not found: ${CARLA_ROOT}" >&2
  exit 1
fi

if [[ ! -f "${SCENARIO_RUNNER_ROOT}/scenario_runner.py" ]]; then
  echo "ScenarioRunner 0.9.15 not found: ${SCENARIO_RUNNER_ROOT}" >&2
  exit 1
fi

if [[ "${SKIP_CARLA_PIP_INSTALL:-0}" != "1" ]]; then
  conda run -n yolo pip install \
    "carla==0.9.15" \
    "py-trees==0.8.3" \
    "shapely>=2,<3" \
    "xmlschema>=2,<4" \
    ephem tabulate six simple-watchdog-timer "antlr4-python3-runtime==4.10" graphviz
fi

if git -C "${SCENARIO_RUNNER_ROOT}" apply --check "${REPO_ROOT}/patches/scenario_runner_0.9.15_py310.patch" 2>/dev/null; then
  git -C "${SCENARIO_RUNNER_ROOT}" apply "${REPO_ROOT}/patches/scenario_runner_0.9.15_py310.patch"
  echo "Applied ScenarioRunner Python 3.10 compatibility patch."
elif git -C "${SCENARIO_RUNNER_ROOT}" apply --reverse --check \
  "${REPO_ROOT}/patches/scenario_runner_0.9.15_py310.patch" 2>/dev/null; then
  echo "ScenarioRunner compatibility patch is already applied."
else
  echo "ScenarioRunner tree does not match the expected v0.9.15 source." >&2
  exit 1
fi

conda run -n yolo python -c "import carla; assert carla.Client"
echo "CARLA 0.9.15 client and ScenarioRunner source are ready."
