#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${ZHJ_DATA_ROOT:-/data5/lzx_data/Zhijia-Guardian}"
CARLA_ROOT="${CARLA_ROOT:-${DATA_ROOT}/third_party/carla/0.9.15/runtime}"
CARLA_PORT="${CARLA_PORT:-2000}"
CARLA_RENDER_MODE="${CARLA_RENDER_MODE:-offscreen}"

if [[ ! -x "${CARLA_ROOT}/CarlaUE4.sh" ]]; then
  echo "CARLA runtime not found: ${CARLA_ROOT}" >&2
  exit 1
fi

if [[ "${CARLA_RENDER_MODE}" == "xvfb" ]]; then
  exec xvfb-run -a -s "-screen 0 1280x720x24" \
    "${CARLA_ROOT}/CarlaUE4.sh" \
    -quality-level=Low \
    -nosound \
    "-carla-rpc-port=${CARLA_PORT}" \
    "$@"
fi

if [[ "${CARLA_RENDER_MODE}" != "offscreen" ]]; then
  echo "Unsupported CARLA_RENDER_MODE: ${CARLA_RENDER_MODE} (use offscreen or xvfb)" >&2
  exit 1
fi

exec "${CARLA_ROOT}/CarlaUE4.sh" \
  -RenderOffScreen \
  -quality-level=Low \
  -nosound \
  "-carla-rpc-port=${CARLA_PORT}" \
  "$@"
