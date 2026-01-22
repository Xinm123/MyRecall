#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SERVER_CMD="cd \"$ROOT_DIR\" && bash \"$ROOT_DIR/scripts/run_server.sh\""
CLIENT_CMD="cd \"$ROOT_DIR\" && bash \"$ROOT_DIR/scripts/run_client.sh\""

osascript >/dev/null <<OSA
tell application "Terminal"
  activate
  set serverTab to do script "$SERVER_CMD"
  delay 0.4
  tell application "System Events" to keystroke "t" using command down
  delay 0.2
  do script "$CLIENT_CMD" in front window
end tell
OSA
