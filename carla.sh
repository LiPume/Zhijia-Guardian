#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${ZHJ_DATA_ROOT:-/data5/lzx_data/Zhijia-Guardian}"
CARLA_ROOT="${CARLA_ROOT:-${DATA_ROOT}/third_party/carla/0.9.15/runtime}"
CARLA_PORT="${CARLA_PORT:-2000}"

if [[ ! -x "${CARLA_ROOT}/CarlaUE4.sh" ]]; then
  echo "CARLA runtime not found: ${CARLA_ROOT}" >&2
  exit 1
fi

exec "${CARLA_ROOT}/CarlaUE4.sh" \
  -RenderOffScreen \
  -quality-level=Low \
  -nosound \
  "-carla-rpc-port=${CARLA_PORT}" \
  "$@"
