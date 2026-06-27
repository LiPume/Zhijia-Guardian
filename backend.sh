#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_NAME="${CONDA_ENV:-yolo}"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  ./backend.sh

Environment variables:
  CONDA_ENV              Conda environment name. Default: yolo
  SEED                   Random seed. Default: 42
  COUNT                  Manual scenario count. Default: 72
  DATASET                Canonical manual dataset path. Default: data/sample_scenarios/manual_json/v0_1
  OUTPUT_ROOT            Run output root. Default: /data5/lzx_data/Zhijia-Guardian/outputs/runs
  GENERATE               Generate manual scenarios before eval. Default: 1
  CLEAN                  Clean dataset directory during generation. Default: 1
  RUN_RULE_ONLY          Run rule-only baseline. Default: 1
  RUN_MULTI_AGENT        Run multi-agent tools method. Default: 1
  RUN_SINGLE_LLM         Run the API-backed Single-LLM baseline. Default: 0
  RULE_RUN_ID            Rule-only run id. Default: manual_v0_1_noisy_rule_seed${SEED}
  MULTI_RUN_ID           Multi-agent run id. Default: manual_v0_1_noisy_multi_agent_seed${SEED}
  SINGLE_LLM_RUN_ID      Single-LLM run id. Default: manual_v0_1_noisy_single_llm_seed${SEED}
  SINGLE_LLM_LIMIT       Limit API calls to the first N scenarios; 0 means all. Default: 0
  LLM_CONFIG             LLM config path. Default: configs/llm.yaml
  OPENAI_API_KEY         Required only when RUN_SINGLE_LLM=1
  OPENAI_BASE_URL        Optional OpenAI-compatible API base URL
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
SEED="${SEED:-42}"
COUNT="${COUNT:-72}"
DATASET="${DATASET:-data/sample_scenarios/manual_json/v0_1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/data5/lzx_data/Zhijia-Guardian/outputs/runs}"
GENERATE="${GENERATE:-1}"
CLEAN="${CLEAN:-1}"
RUN_RULE_ONLY="${RUN_RULE_ONLY:-1}"
RUN_MULTI_AGENT="${RUN_MULTI_AGENT:-1}"
RUN_SINGLE_LLM="${RUN_SINGLE_LLM:-0}"
RULE_RUN_ID="${RULE_RUN_ID:-manual_v0_1_noisy_rule_seed${SEED}}"
MULTI_RUN_ID="${MULTI_RUN_ID:-manual_v0_1_noisy_multi_agent_seed${SEED}}"
SINGLE_LLM_RUN_ID="${SINGLE_LLM_RUN_ID:-manual_v0_1_noisy_single_llm_seed${SEED}}"
SINGLE_LLM_LIMIT="${SINGLE_LLM_LIMIT:-0}"
LLM_CONFIG="${LLM_CONFIG:-configs/llm.yaml}"

mkdir -p "$OUTPUT_ROOT"

echo "[backend] repo: $ROOT_DIR"
echo "[backend] env:  $CONDA_ENV_NAME"
echo "[backend] data: $DATASET"
echo "[backend] out:  $OUTPUT_ROOT"

if [[ "$GENERATE" == "1" ]]; then
  clean_arg=()
  if [[ "$CLEAN" == "1" ]]; then
    clean_arg=(--clean)
  fi
  echo "[backend] generating manual scenarios..."
  "$PYTHON" scripts/generate_manual_scenarios.py \
    --output "$DATASET" \
    --count "$COUNT" \
    --seed "$SEED" \
    "${clean_arg[@]}"
fi

if [[ "$RUN_RULE_ONLY" == "1" ]]; then
  echo "[backend] running rule-only baseline..."
  "$PYTHON" experiments/run_eval.py \
    --method rule_only \
    --dataset "$DATASET" \
    --run-id "$RULE_RUN_ID" \
    --output-root "$OUTPUT_ROOT" \
    --seed "$SEED"
fi

if [[ "$RUN_MULTI_AGENT" == "1" ]]; then
  echo "[backend] running multi-agent tools..."
  "$PYTHON" experiments/run_eval.py \
    --method multi_agent_tools \
    --dataset "$DATASET" \
    --run-id "$MULTI_RUN_ID" \
    --output-root "$OUTPUT_ROOT" \
    --seed "$SEED"
fi

if [[ "$RUN_SINGLE_LLM" == "1" ]]; then
  limit_arg=()
  if [[ "$SINGLE_LLM_LIMIT" != "0" ]]; then
    limit_arg=(--limit "$SINGLE_LLM_LIMIT")
  fi
  echo "[backend] running Single-LLM baseline..."
  "$PYTHON" experiments/run_eval.py \
    --method single_llm \
    --dataset "$DATASET" \
    --run-id "$SINGLE_LLM_RUN_ID" \
    --output-root "$OUTPUT_ROOT" \
    --seed "$SEED" \
    --llm-config "$LLM_CONFIG" \
    --enable-llm \
    "${limit_arg[@]}"
fi

echo "[backend] done"
if [[ "$RUN_RULE_ONLY" == "1" ]]; then
  echo "[backend] rule report:  $OUTPUT_ROOT/$RULE_RUN_ID/run_report.md"
fi
if [[ "$RUN_MULTI_AGENT" == "1" ]]; then
  echo "[backend] multi report: $OUTPUT_ROOT/$MULTI_RUN_ID/run_report.md"
fi
if [[ "$RUN_SINGLE_LLM" == "1" ]]; then
  echo "[backend] LLM report:   $OUTPUT_ROOT/$SINGLE_LLM_RUN_ID/run_report.md"
fi
