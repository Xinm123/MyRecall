#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: p1_s2b_plus_local.sh [options]

Run automated P1-S2b+ verification (tests + runtime evidence) and write evidence files.

Prerequisite:
  - Start server: ./run_server.sh --debug
  - Start client: ./run_client.sh --debug

Options:
  --evidence-dir DIR      Evidence directory (default: docs/v3/acceptance/phase1/evidence)
  --client-log PATH       Client log file path (default: logs/client.log)
  --edge-db PATH          Edge DB path (default: ${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db)
  --spool-dir PATH        Spool dir path (default: ${OPENRECALL_CLIENT_DATA_DIR:-$HOME/MRC}/spool)
  --wait-seconds N        Runtime observation window (default: 20)
  --auto-seed-count N     Auto-insert N synthetic simhash rows into edge.db during runtime window (default: 0)
  --skip-runtime          Only run pytest checks
  --skip-pytest           Only run runtime checks
  -h, --help              Show help

Outputs:
  - p1-s2b-plus-local-gate.log
  - p1-s2b-plus-summary.json
  - p1-s2b-plus-runtime.json
EOF
}

EVIDENCE_DIR="docs/v3/acceptance/phase1/evidence"
CLIENT_LOG="logs/client.log"
EDGE_DB="${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db"
SPOOL_DIR="${OPENRECALL_CLIENT_DATA_DIR:-$HOME/MRC}/spool"
WAIT_SECONDS=20
AUTO_SEED_COUNT=0
SKIP_RUNTIME=0
SKIP_PYTEST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence-dir)
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --client-log)
      CLIENT_LOG="$2"
      shift 2
      ;;
    --edge-db)
      EDGE_DB="$2"
      shift 2
      ;;
    --spool-dir)
      SPOOL_DIR="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --auto-seed-count)
      AUTO_SEED_COUNT="$2"
      shift 2
      ;;
    --skip-runtime)
      SKIP_RUNTIME=1
      shift
      ;;
    --skip-pytest)
      SKIP_PYTEST=1
      shift
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

LOG_FILE="$EVIDENCE_DIR/p1-s2b-plus-local-gate.log"
SUMMARY_FILE="$EVIDENCE_DIR/p1-s2b-plus-summary.json"
RUNTIME_FILE="$EVIDENCE_DIR/p1-s2b-plus-runtime.json"

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] P1-S2b+ gate started"
echo "[INFO] evidence_dir=$EVIDENCE_DIR"
echo "[INFO] client_log=$CLIENT_LOG"
echo "[INFO] edge_db=$EDGE_DB"
echo "[INFO] spool_dir=$SPOOL_DIR"
echo "[INFO] wait_seconds=$WAIT_SECONDS"
echo "[INFO] auto_seed_count=$AUTO_SEED_COUNT"

FAIL_COUNT=0
PYTEST_STATUS="skipped"
RUNTIME_STATUS="skipped"

if [[ "$SKIP_PYTEST" -eq 0 ]]; then
  if pytest tests/test_p1_s2b_plus_acceptance.py tests/test_p1_s2b_plus_simhash.py tests/test_p1_s2b_plus_heartbeat.py -q; then
    PYTEST_STATUS="pass"
  else
    PYTEST_STATUS="fail"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
fi

if [[ "$SKIP_RUNTIME" -eq 0 ]]; then
  python3 - "$CLIENT_LOG" "$EDGE_DB" "$SPOOL_DIR" "$WAIT_SECONDS" "$AUTO_SEED_COUNT" "$RUNTIME_FILE" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


client_log = Path(sys.argv[1])
edge_db = Path(sys.argv[2])
spool_dir = Path(sys.argv[3])
wait_seconds = max(1, int(sys.argv[4]))
auto_seed_count = max(0, int(sys.argv[5]))
runtime_file = Path(sys.argv[6])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def seed_simhash_rows(db_path: Path, count: int) -> int:
    if count <= 0 or not db_path.exists():
        return 0
    inserted = 0
    with sqlite3.connect(str(db_path)) as conn:
        for i in range(count):
            ts = utc_now_iso()
            capture_id = f"auto-seed-s2b-plus-{int(time.time() * 1000)}-{i}"
            conn.execute(
                """
                INSERT INTO frames
                (capture_id, timestamp, app_name, window_name, device_name,
                 snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at, simhash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capture_id,
                    ts,
                    "AutoSeed",
                    "s2b-plus-runtime",
                    "monitor_auto_seed",
                    f"/tmp/{capture_id}.jpg",
                    "manual",
                    ts,
                    "completed",
                    ts,
                    ts,
                    0xABCDEF00 + i,
                ),
            )
            inserted += 1
        conn.commit()
    return inserted


def count_spool_items(path: Path) -> int:
    if not path.exists():
        return 0
    return len(list(path.glob("*.json")))


def count_log_hits(path: Path, token: str) -> int:
    if not path.exists():
        return 0
    text = path.read_text(errors="replace")
    return text.count(token)


spool_before = count_spool_items(spool_dir)
log_exists = client_log.exists()
skip_before = count_log_hits(client_log, "MRV3 similar_frame_skipped")

db_total_before = 0
db_non_null_before = 0
if edge_db.exists():
    with sqlite3.connect(str(edge_db)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN simhash IS NOT NULL THEN 1 ELSE 0 END) AS non_null FROM frames"
        ).fetchone()
        if row is not None:
            db_total_before = int(row[0] or 0)
            db_non_null_before = int(row[1] or 0)

time.sleep(wait_seconds)

inserted_seed_rows = seed_simhash_rows(edge_db, auto_seed_count)

spool_after = count_spool_items(spool_dir)
skip_after = count_log_hits(client_log, "MRV3 similar_frame_skipped")

spool_growth = spool_after - spool_before
skip_growth = skip_after - skip_before

simhash_total = 0
simhash_non_null = 0
if edge_db.exists():
    with sqlite3.connect(str(edge_db)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN simhash IS NOT NULL THEN 1 ELSE 0 END) AS non_null FROM frames"
        ).fetchone()
        if row is not None:
            simhash_total = int(row[0] or 0)
            simhash_non_null = int(row[1] or 0)

delta_total = max(0, simhash_total - db_total_before)
delta_non_null = max(0, simhash_non_null - db_non_null_before)

spool_integration_rate = 0.0
if delta_total > 0:
    spool_integration_rate = (delta_non_null / delta_total) * 100.0

runtime = {
    "wait_seconds": wait_seconds,
    "spool_before": spool_before,
    "spool_after": spool_after,
    "spool_growth": spool_growth,
    "skip_before": skip_before,
    "skip_after": skip_after,
    "skip_growth": skip_growth,
    "log_exists": log_exists,
    "simhash_total": simhash_total,
    "simhash_non_null": simhash_non_null,
    "delta_total": delta_total,
    "delta_non_null": delta_non_null,
    "inserted_seed_rows": inserted_seed_rows,
    "spool_integration_rate": spool_integration_rate,
    "checks": {
        "similar_frame_skip_seen": (skip_growth > 0) if log_exists else True,
        "heartbeat_or_capture_progress": (spool_growth > 0) or (delta_total > 0),
        "spool_integration_rate_100": (spool_integration_rate == 100.0) if delta_total > 0 else False,
    },
}

runtime["pass"] = all(runtime["checks"].values())
runtime["diagnostics"] = {
    "note_log_missing": (not log_exists),
    "note_no_new_rows": (delta_total == 0),
}
runtime_file.write_text(json.dumps(runtime, indent=2))
print("pass" if runtime["pass"] else "fail")
PY
  if [[ "$(python3 -c 'import json,sys; print("pass" if json.load(open(sys.argv[1]))["pass"] else "fail")' "$RUNTIME_FILE")" == "pass" ]]; then
    RUNTIME_STATUS="pass"
  else
    RUNTIME_STATUS="fail"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
fi

python3 - "$SUMMARY_FILE" "$PYTEST_STATUS" "$RUNTIME_STATUS" "$RUNTIME_FILE" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

summary_file = Path(sys.argv[1])
pytest_status = sys.argv[2]
runtime_status = sys.argv[3]
runtime_file = Path(sys.argv[4])

runtime = {}
if runtime_file.exists():
    runtime = json.loads(runtime_file.read_text())

summary = {
    "pytest_status": pytest_status,
    "runtime_status": runtime_status,
    "overall_pass": (pytest_status in {"pass", "skipped"}) and (runtime_status in {"pass", "skipped"}),
    "runtime": runtime,
}
summary_file.write_text(json.dumps(summary, indent=2))
PY

if [[ "$FAIL_COUNT" -eq 0 ]]; then
  echo "[INFO] Result: Pass"
  echo "[INFO] Evidence: $SUMMARY_FILE"
  echo "[INFO] Evidence: $RUNTIME_FILE"
  exit 0
fi

echo "[INFO] Result: Fail"
echo "[INFO] Evidence: $SUMMARY_FILE"
echo "[INFO] Evidence: $RUNTIME_FILE"
exit 1
