#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_NAME="${CONDA_ENV:-yolo}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  ./frontend.sh

Environment variables:
  CONDA_ENV       Conda environment name. Default: yolo
  HOST            Streamlit host. Default: 0.0.0.0
  PORT            Preferred Streamlit port. Default: 8501
  AUTO_PORT       If PORT is busy, try the next port. Default: 1
  OUTPUT_ROOT     Read by the UI sidebar by default. Default: /data5/lzx_data/Zhijia-Guardian/outputs/runs
EOF
  exit 0
fi

if [[ -f "$CONDA_SH" ]]; then
  # shellcheck source=/dev/null
  source "$CONDA_SH"
  conda activate "$CONDA_ENV_NAME"
else
  echo "Could not find conda activation script: $CONDA_SH" >&2
  exit 1
fi

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"

PYTHON="${PYTHON:-python}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8501}"
AUTO_PORT="${AUTO_PORT:-1}"
export OUTPUT_ROOT="${OUTPUT_ROOT:-/data5/lzx_data/Zhijia-Guardian/outputs/runs}"

port_is_free() {
  "$PYTHON" - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) != 0 else 1)
PY
}

if [[ "$AUTO_PORT" == "1" ]]; then
  while ! port_is_free "$PORT"; do
    PORT=$((PORT + 1))
  done
elif ! port_is_free "$PORT"; then
  echo "Port $PORT is already in use. Set PORT=... or AUTO_PORT=1." >&2
  exit 1
fi

echo "[frontend] repo: $ROOT_DIR"
echo "[frontend] env:  $CONDA_ENV_NAME"
echo "[frontend] root: $OUTPUT_ROOT"
echo "[frontend] url:  http://127.0.0.1:$PORT"

exec "$PYTHON" -m streamlit run app/streamlit_app.py \
  --server.headless=true \
  --server.address="$HOST" \
  --server.port="$PORT"
