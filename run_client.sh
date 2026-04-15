#!/usr/bin/env bash
# NOTE: Renamed from run_client_foreground.sh
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

config_file=""
env_file=""
mode=""
config_explicit=""
enable_debug="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --debug)
      enable_debug="true"
      shift
      ;;
    --no-web)
      shift
      ;;
    --mode=*)
      mode="${1#--mode=}"
      shift
      ;;
    --mode)
      shift
      mode="${1:-}"
      shift
      ;;
    --config=*)
      if [[ -n "$mode" ]]; then
        echo "[Mode] --config takes precedence over --mode" >&2
      fi
      config_file="${1#--config=}"
      config_explicit="true"
      shift
      ;;
    --config)
      shift
      if [[ -n "$mode" ]]; then
        echo "[Mode] --config takes precedence over --mode" >&2
      fi
      config_file="${1:-}"
      config_explicit="true"
      shift
      ;;
    --env=*)
      env_file="${1#--env=}"
      shift
      ;;
    --env)
      shift
      env_file="${1:-}"
      shift
      ;;
    *)
      echo "Usage: $0 [--debug] [--no-web] [--mode local|remote] [--config=/abs/path/to/client.toml] [--env=/abs/path/to/myrecall_client.env]" >&2
      exit 2
      ;;
  esac
done

# Mode-based config selection (only if --config was not explicitly provided)
# Spec: --config takes precedence over --mode (explicit override wins)
if [[ -n "$mode" && -z "$config_file" ]]; then
  case "$mode" in
    local)
      config_file="$repo_root/client-local.toml"
      ;;
    remote)
      config_file="$repo_root/client-remote.toml"
      ;;
    *)
      echo "Error: unknown --mode value '$mode'. Use 'local' or 'remote'." >&2
      echo "Usage: $0 [--debug] [--mode local|remote] [--config=/abs/path] [--env=/abs/path]" >&2
      exit 2
      ;;
  esac
  echo "[Mode] Loading config: $config_file"
fi

# Config source priority: --config (TOML) > --env (legacy) > default paths
if [[ -z "$config_file" && -z "$env_file" ]]; then
  if [[ -f "$repo_root/client.toml" ]]; then
    config_file="$repo_root/client.toml"
  elif [[ -f "$HOME/.myrecall/client.toml" ]]; then
    config_file="$HOME/.myrecall/client.toml"
  elif [[ -f "$repo_root/myrecall_client.env" ]]; then
    env_file="$repo_root/myrecall_client.env"
  elif [[ -f "$HOME/.myrecall/myrecall_client.env" ]]; then
    env_file="$HOME/.myrecall/myrecall_client.env"
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

# python_bin="${OPENRECALL_PYTHON_BIN:-/data/venvs/openrecall/bin/python}"
# if [[ ! -x "$python_bin" ]]; then
#   python_bin="$(command -v python3 || true)"
# fi
# if [[ -z "${python_bin:-}" ]]; then
#   echo "Python not found. Set OPENRECALL_PYTHON_BIN to your venv python." >&2
#   exit 1
# fi

# # Build command arguments
# cmd_args=()
# if [[ -n "$config_file" ]]; then
#   cmd_args+=("--config" "$config_file")
# fi

# exec "$python_bin" -m openrecall.client "${cmd_args[@]}" "$@"
# Verify Python is available
if ! command -v python &> /dev/null; then
  echo "Error: python not found. Activate your conda/venv environment first." >&2
  exit 1
fi

# Build command arguments
cmd_args=("-m" "openrecall.client")
if [[ -n "$config_file" ]]; then
  cmd_args+=("--config" "$config_file")
fi

exec python "${cmd_args[@]}"
