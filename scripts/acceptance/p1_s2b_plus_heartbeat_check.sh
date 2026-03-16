#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: p1_s2b_plus_heartbeat_check.sh [options]

Minimal runtime check for P1-S2b+ heartbeat force-enqueue behavior.

Prerequisite:
  - Server and client are already running.
  - Client is configured with simhash dedup enabled.

Options:
  --client-log PATH      Client log file path (default: /tmp/myrecall-client.log)
  --edge-db PATH         Edge DB path (default: ${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db)
  --heartbeat-sec N      Heartbeat threshold seconds (default: 10)
  --idle-interval-sec N  Idle trigger interval seconds (default: OPENRECALL_IDLE_CAPTURE_INTERVAL_MS/1000 or 30)
  --padding-sec N        Extra observation seconds after threshold (default: 5)
  --evidence-dir DIR     Evidence output directory (default: docs/v3/acceptance/phase1/evidence)
  -h, --help             Show help

Outputs:
  - p1-s2b-plus-heartbeat.log
  - p1-s2b-plus-heartbeat-result.json
EOF
}

CLIENT_LOG="/tmp/myrecall-client.log"
EDGE_DB="${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db"
HEARTBEAT_SEC=10
IDLE_INTERVAL_SEC=""
PADDING_SEC=5
EVIDENCE_DIR="docs/v3/acceptance/phase1/evidence"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client-log)
      CLIENT_LOG="$2"
      shift 2
      ;;
    --edge-db)
      EDGE_DB="$2"
      shift 2
      ;;
    --heartbeat-sec)
      HEARTBEAT_SEC="$2"
      shift 2
      ;;
    --idle-interval-sec)
      IDLE_INTERVAL_SEC="$2"
      shift 2
      ;;
    --padding-sec)
      PADDING_SEC="$2"
      shift 2
      ;;
    --evidence-dir)
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

mkdir -p "$EVIDENCE_DIR"

if [[ -z "$IDLE_INTERVAL_SEC" ]]; then
  if [[ -n "${OPENRECALL_IDLE_CAPTURE_INTERVAL_MS:-}" ]]; then
    IDLE_INTERVAL_SEC=$((OPENRECALL_IDLE_CAPTURE_INTERVAL_MS / 1000))
  else
    IDLE_INTERVAL_SEC=30
  fi
fi

LOG_FILE="$EVIDENCE_DIR/p1-s2b-plus-heartbeat.log"
RESULT_FILE="$EVIDENCE_DIR/p1-s2b-plus-heartbeat-result.json"
REQUESTED_WAIT_SECONDS=$((HEARTBEAT_SEC + PADDING_SEC))
MIN_WAIT_SECONDS=$((IDLE_INTERVAL_SEC * 2 + PADDING_SEC))
if (( REQUESTED_WAIT_SECONDS < MIN_WAIT_SECONDS )); then
  WAIT_SECONDS=$MIN_WAIT_SECONDS
else
  WAIT_SECONDS=$REQUESTED_WAIT_SECONDS
fi

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] Heartbeat check started"
echo "[INFO] client_log=$CLIENT_LOG"
echo "[INFO] edge_db=$EDGE_DB"
echo "[INFO] heartbeat_sec=$HEARTBEAT_SEC"
echo "[INFO] idle_interval_sec=$IDLE_INTERVAL_SEC"
echo "[INFO] padding_sec=$PADDING_SEC"
echo "[INFO] requested_wait_seconds=$REQUESTED_WAIT_SECONDS"
echo "[INFO] min_wait_seconds=$MIN_WAIT_SECONDS"
echo "[INFO] wait_seconds=$WAIT_SECONDS"
echo "[INFO] Keep the screen static during this window."

python3 - "$CLIENT_LOG" "$EDGE_DB" "$WAIT_SECONDS" "$HEARTBEAT_SEC" "$IDLE_INTERVAL_SEC" "$RESULT_FILE" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path


client_log = Path(sys.argv[1])
edge_db = Path(sys.argv[2])
wait_seconds = max(1, int(sys.argv[3]))
heartbeat_sec = max(1, int(sys.argv[4]))
idle_interval_sec = max(1, int(sys.argv[5]))
result_file = Path(sys.argv[6])


def count_skips(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return log_path.read_text(errors="replace").count("MRV3 similar_frame_skipped")


def count_enqueue_logs(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return log_path.read_text(errors="replace").count("trigger_queue=")


def count_heartbeat_force_enqueue_logs(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return log_path.read_text(errors="replace").count("MRV3 heartbeat_force_enqueue")


def spool_count() -> int:
    spool_dir = Path.home() / "MRC" / "spool"
    if not spool_dir.exists():
        return 0
    return len(list(spool_dir.glob("*.json")))


def frame_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM frames").fetchone()
        return int(row[0] if row else 0)


skip_before = count_skips(client_log)
enqueue_before = count_enqueue_logs(client_log)
heartbeat_force_enqueue_before = count_heartbeat_force_enqueue_logs(client_log)
frames_before = frame_count(edge_db)
spool_before = spool_count()

time.sleep(wait_seconds)

skip_after = count_skips(client_log)
enqueue_after = count_enqueue_logs(client_log)
heartbeat_force_enqueue_after = count_heartbeat_force_enqueue_logs(client_log)
frames_after = frame_count(edge_db)
spool_after = spool_count()

skip_growth = max(0, skip_after - skip_before)
frame_growth = max(0, frames_after - frames_before)
enqueue_growth = max(0, enqueue_after - enqueue_before)
heartbeat_force_enqueue_growth = max(
    0, heartbeat_force_enqueue_after - heartbeat_force_enqueue_before
)
spool_growth = max(0, spool_after - spool_before)

result = {
    "wait_seconds": wait_seconds,
    "heartbeat_sec": heartbeat_sec,
    "idle_interval_sec": idle_interval_sec,
    "skip_before": skip_before,
    "skip_after": skip_after,
    "skip_growth": skip_growth,
    "enqueue_before": enqueue_before,
    "enqueue_after": enqueue_after,
    "enqueue_growth": enqueue_growth,
    "heartbeat_force_enqueue_before": heartbeat_force_enqueue_before,
    "heartbeat_force_enqueue_after": heartbeat_force_enqueue_after,
    "heartbeat_force_enqueue_growth": heartbeat_force_enqueue_growth,
    "spool_before": spool_before,
    "spool_after": spool_after,
    "spool_growth": spool_growth,
    "frames_before": frames_before,
    "frames_after": frames_after,
    "frame_growth": frame_growth,
    "checks": {
      "heartbeat_forced_enqueue_observed": (frame_growth >= 1) or (enqueue_growth >= 1) or (spool_growth >= 1),
      "heartbeat_forced_enqueue_log_observed": heartbeat_force_enqueue_growth > 0,
      "similar_frames_are_being_dropped": skip_growth > 0,
    },
    "diagnostics": {
      "client_log_exists": client_log.exists(),
      "edge_db_exists": edge_db.exists(),
      "drop_check_required": heartbeat_sec > idle_interval_sec,
      "likely_client_restart_needed": False,
    },
}

if (
    result["checks"]["heartbeat_forced_enqueue_observed"]
    and (not result["checks"]["heartbeat_forced_enqueue_log_observed"])
):
    result["diagnostics"]["likely_client_restart_needed"] = True

if heartbeat_sec > idle_interval_sec:
    result["pass"] = (
        result["checks"]["heartbeat_forced_enqueue_observed"]
        and result["checks"]["similar_frames_are_being_dropped"]
    )
else:
    result["pass"] = result["checks"]["heartbeat_forced_enqueue_observed"]

if (
    result["checks"]["heartbeat_forced_enqueue_observed"]
    and not result["checks"]["heartbeat_forced_enqueue_log_observed"]
):
    result["diagnostics"]["force_enqueue_log_missing_but_behavior_observed"] = True
else:
    result["diagnostics"]["force_enqueue_log_missing_but_behavior_observed"] = False

result_file.write_text(json.dumps(result, indent=2))
print("pass" if result["pass"] else "fail")
PY

if [[ "$(python3 -c 'import json,sys; print("pass" if json.load(open(sys.argv[1]))["pass"] else "fail")' "$RESULT_FILE")" == "pass" ]]; then
  echo "[INFO] Result: Pass"
  echo "[INFO] Evidence: $RESULT_FILE"
  exit 0
fi

echo "[INFO] Result: Fail"
echo "[INFO] Evidence: $RESULT_FILE"
exit 1
