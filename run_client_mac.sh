#!/usr/bin/env bash
set -euo pipefail

SERVER_IP="${OPENRECALL_SERVER_IP:-10.77.45.162}"
SERVER_PORT="${OPENRECALL_SERVER_PORT:-18083}"
API_URL="http://${SERVER_IP}:${SERVER_PORT}/api"

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

env_file="${OPENRECALL_ENV_FILE:-$repo_root/openrecall_client.env}"

if [[ ! -f "$env_file" ]]; then
  cat > "$env_file" <<EOF
OPENRECALL_DEBUG=true
OPENRECALL_API_URL=${API_URL}
OPENRECALL_CAPTURE_INTERVAL=10
OPENRECALL_PRIMARY_MONITOR_ONLY=true
EOF
  echo "Created $env_file"
fi

if command -v curl >/dev/null 2>&1; then
  echo "Checking server health: ${API_URL}/health"
  curl -fsS "${API_URL}/health" >/dev/null || {
    echo "Server not reachable: ${API_URL}/health" >&2
    exit 1
  }
fi

set -a
source "$env_file"
set +a

python_bin="${OPENRECALL_PYTHON_BIN:-}"
if [[ -z "${python_bin}" ]]; then
  if [[ -x "$repo_root/.venv/bin/python" ]]; then
    python_bin="$repo_root/.venv/bin/python"
  elif [[ -x "$repo_root/venv/bin/python" ]]; then
    python_bin="$repo_root/venv/bin/python"
  else
    python_bin="$(command -v python3 || true)"
  fi
fi

if [[ -z "${python_bin}" ]]; then
  echo "Python not found. Please install Python 3 and dependencies first." >&2
  exit 1
fi

echo "Starting OpenRecall client..."
echo "API: ${OPENRECALL_API_URL:-$API_URL}"
exec "$python_bin" -m openrecall.client