#!/usr/bin/env bash
# Standalone launcher for low-latency profile.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

env_file="${OPENRECALL_ENV_FILE:-$repo_root/myrecall_client_low_latency.env}"
enable_debug="false"

for arg in "$@"; do
  case "$arg" in
    --debug)
      enable_debug="true"
      ;;
    --env=*)
      env_file="${arg#--env=}"
      ;;
    *)
      echo "Usage: $0 [--debug] [--env=/abs/path/to/myrecall_client_low_latency.env]" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$env_file" ]]; then
  echo "Env file not found: $env_file" >&2
  exit 1
fi

set -a
source "$env_file"
set +a

if [[ "$enable_debug" == "true" ]]; then
  export OPENRECALL_DEBUG=true
fi

python_bin="${OPENRECALL_PYTHON_BIN:-/data/venvs/openrecall/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
fi
if [[ -z "${python_bin:-}" ]]; then
  echo "Python not found. Set OPENRECALL_PYTHON_BIN to your venv python." >&2
  exit 1
fi

echo "[run_client_low_latency] env_file=$env_file"

exec "$python_bin" -m openrecall.client
