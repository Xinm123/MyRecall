#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OPENRECALL_CONDA_ENV="${OPENRECALL_CONDA_ENV:-MyRecall}"
OPENRECALL_PYTHON="${OPENRECALL_PYTHON:-python}"
OPENRECALL_USE_CONDA="${OPENRECALL_USE_CONDA:-auto}"
OPENRECALL_LOG_FILE="${OPENRECALL_LOG_FILE:-}"

export OPENRECALL_DATA_DIR="${OPENRECALL_DATA_DIR:-$ROOT_DIR/.openrecall_data}"
export OPENRECALL_HOST="${OPENRECALL_HOST:-127.0.0.1}"
export OPENRECALL_PORT="${OPENRECALL_PORT:-8083}"
export OPENRECALL_DEBUG="${OPENRECALL_DEBUG:-true}"
export OPENRECALL_PRELOAD_MODELS="${OPENRECALL_PRELOAD_MODELS:-false}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

echo "OpenRecall server starting..."
echo "  data_dir=$OPENRECALL_DATA_DIR"
echo "  bind=$OPENRECALL_HOST:$OPENRECALL_PORT"
echo "  debug=$OPENRECALL_DEBUG preload_models=$OPENRECALL_PRELOAD_MODELS"

if [[ "$OPENRECALL_USE_CONDA" != "false" && "$OPENRECALL_USE_CONDA" != "0" ]] && command -v conda >/dev/null 2>&1; then
  if [[ -n "$OPENRECALL_LOG_FILE" ]]; then
    conda run -n "$OPENRECALL_CONDA_ENV" "$OPENRECALL_PYTHON" -u -m openrecall.server 2>&1 | tee -a "$OPENRECALL_LOG_FILE"
    exit $?
  fi
  exec conda run -n "$OPENRECALL_CONDA_ENV" "$OPENRECALL_PYTHON" -u -m openrecall.server
fi

if [[ -n "$OPENRECALL_LOG_FILE" ]]; then
  "$OPENRECALL_PYTHON" -u -m openrecall.server 2>&1 | tee -a "$OPENRECALL_LOG_FILE"
  exit $?
fi

exec "$OPENRECALL_PYTHON" -u -m openrecall.server
