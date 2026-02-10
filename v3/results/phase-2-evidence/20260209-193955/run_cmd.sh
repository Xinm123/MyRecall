#!/usr/bin/env bash
set -euo pipefail
: "${CMD_LOG:?CMD_LOG is required}"
run_cmd() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] CMD: $*" | tee -a "$CMD_LOG"
  # Mirror command output to commands.log without creating a pipeline around eval,
  # so rc is the true command exit code.
  eval "$@" > >(tee -a "$CMD_LOG") 2> >(tee -a "$CMD_LOG" >&2)
  local rc=$?
  echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] EXIT: $rc" | tee -a "$CMD_LOG"
  return $rc
}
