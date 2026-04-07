#!/usr/bin/env bash
# NOTE: Renamed from run_server_foreground.sh
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

config_file=""
env_file=""
mode=""
enable_debug="false"

for arg in "$@"; do
  case "$arg" in
    --debug)
      enable_debug="true"
      ;;
    --config=*)
      if [[ -n "$mode" ]]; then
        echo "[Mode] --config takes precedence over --mode" >&2
      fi
      config_file="${arg#--config=}"
      ;;
    --env=*)
      env_file="${arg#--env=}"
      ;;
    --mode=*)
      mode="${arg#--mode=}"
      ;;
    --mode)
      shift
      mode="${1:-}"
      ;;
    *)
      echo "Usage: $0 [--debug] [--mode local|remote] [--config=/abs/path/to/server.toml] [--env=/abs/path/to/myrecall_server.env]" >&2
      exit 2
      ;;
  esac
done

# Mode-based config selection (only if --config was not explicitly provided)
# Spec: --config takes precedence over --mode (explicit override wins)
if [[ -n "$mode" && -z "$config_file" ]]; then
  case "$mode" in
    local)
      config_file="$repo_root/server-local.toml"
      ;;
    remote)
      config_file="$repo_root/server-remote.toml"
      ;;
    *)
      echo "Error: unknown --mode value '$mode'. Use 'local' or 'remote'." >&2
      echo "Usage: $0 [--debug] [--mode local|remote] [--config=/abs/path] [--env=/abs/path]" >&2
      exit 2
      ;;
  esac
  echo "[Mode] Loading config: $config_file"
fi

# Config source priority...
# 1. --config flag (TOML)
# 2. --env flag (legacy .env)
# 3. Default: server.toml in repo root, then ~/.myrecall/server.toml
if [[ -z "$config_file" && -z "$env_file" ]]; then
  if [[ -f "$repo_root/server.toml" ]]; then
    config_file="$repo_root/server.toml"
  elif [[ -f "$HOME/.myrecall/server.toml" ]]; then
    config_file="$HOME/.myrecall/server.toml"
  elif [[ -f "$repo_root/myrecall_server.env" ]]; then
    # Legacy fallback
    env_file="$repo_root/myrecall_server.env"
  elif [[ -f "$HOME/.myrecall/myrecall_server.env" ]]; then
    # Legacy fallback
    env_file="$HOME/.myrecall/myrecall_server.env"
  fi
fi

if [[ -n "$config_file" && ! -f "$config_file" ]]; then
  echo "Config file not found: $config_file" >&2
  exit 1
fi

if [[ -n "$env_file" ]]; then
  if [[ ! -f "$env_file" ]]; then
    echo "Env file not found: $env_file" >&2
    exit 1
  fi
  set -a
  source "$env_file"
  set +a
fi

if [[ "$enable_debug" == "true" ]]; then
  export OPENRECALL_DEBUG=true
fi

python_bin="${OPENRECALL_PYTHON_BIN:-$(pwd)/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python_bin="$(command -v python3 || true)"
fi
if [[ -z "${python_bin:-}" ]]; then
  echo "Python not found. Set OPENRECALL_PYTHON_BIN to your venv python." >&2
  exit 1
fi

# Build command arguments
cmd_args=("-m" "openrecall.server")
if [[ -n "$config_file" ]]; then
  cmd_args+=("--config" "$config_file")
fi

exec "$python_bin" "${cmd_args[@]}"
