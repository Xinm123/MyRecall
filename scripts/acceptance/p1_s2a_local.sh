#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: p1_s2a_local.sh [options]

Run local P1-S2a gate checks and produce a standard evidence bundle.

Options:
  --base-url URL         Edge base URL (default: http://localhost:${OPENRECALL_PORT:-8083})
  --evidence-dir DIR     Evidence output directory
                         (default: docs/v3/acceptance/phase1/evidence)
  --window-id ID         Custom window_id for this run
  --edge-pid PID         Edge process id for metadata (optional)
  --skip-pytest          Skip pytest checks (still produce evidence files)
  -h, --help             Show this help and exit

Outputs:
  - p1-s2a-local-gate.log
  - p1-s2a-metrics.json
  - p1-s2a-health-snapshots.json
  - p1-s2a-ui-proof.md
EOF
}

BASE_URL="http://localhost:${OPENRECALL_PORT:-8083}"
EVIDENCE_DIR="docs/v3/acceptance/phase1/evidence"
WINDOW_ID=""
EDGE_PID=""
SKIP_PYTEST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --evidence-dir)
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    --window-id)
      WINDOW_ID="$2"
      shift 2
      ;;
    --edge-pid)
      EDGE_PID="$2"
      shift 2
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

RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_TAG="$(date -u +%Y%m%dT%H%M%SZ)"
WINDOW_ID="${WINDOW_ID:-p1-s2a-${RUN_TAG}}"
EDGE_PID="${EDGE_PID:-unknown}"
GIT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
HOSTNAME_VAL="$(hostname 2>/dev/null || echo unknown-host)"

LOG_FILE="$EVIDENCE_DIR/p1-s2a-local-gate.log"
METRICS_FILE="$EVIDENCE_DIR/p1-s2a-metrics.json"
HEALTH_FILE="$EVIDENCE_DIR/p1-s2a-health-snapshots.json"
UI_PROOF_FILE="$EVIDENCE_DIR/p1-s2a-ui-proof.md"

HEALTH_BODY_FILE="$EVIDENCE_DIR/p1-s2a-health-response.json"
QUEUE_BODY_FILE="$EVIDENCE_DIR/p1-s2a-queue-response.json"

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] P1-S2a local gate started"
echo "[INFO] run_ts=$RUN_TS"
echo "[INFO] window_id=$WINDOW_ID"
echo "[INFO] edge_pid=$EDGE_PID"
echo "[INFO] base_url=$BASE_URL"
echo "[INFO] evidence_dir=$EVIDENCE_DIR"
echo "[INFO] git_rev=$GIT_REV"
echo "[INFO] hostname=$HOSTNAME_VAL"

FAIL_COUNT=0
TRIGGER_TEST_STATUS="not_run"
DEBOUNCE_TEST_STATUS="not_run"

run_pytest_check() {
  local test_path="$1"
  local status_var="$2"

  if [[ ! -f "$test_path" ]]; then
    echo "[FAIL] Missing test file: $test_path"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf -v "$status_var" '%s' "missing"
    return
  fi

  if pytest "$test_path" -q; then
    printf -v "$status_var" '%s' "pass"
  else
    printf -v "$status_var" '%s' "fail"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

if [[ "$SKIP_PYTEST" -eq 1 ]]; then
  echo "[INFO] Skipping pytest checks by request (--skip-pytest)"
  TRIGGER_TEST_STATUS="skipped"
  DEBOUNCE_TEST_STATUS="skipped"
else
  run_pytest_check "tests/test_p1_s2a_trigger_coverage.py" TRIGGER_TEST_STATUS
  run_pytest_check "tests/test_p1_s2a_debounce.py" DEBOUNCE_TEST_STATUS
fi

fetch_endpoint() {
  local endpoint="$1"
  local output_file="$2"
  local status_var="$3"
  local code_var="$4"

  local http_code
  http_code="$(curl -sS -m 5 -o "$output_file" -w '%{http_code}' "${BASE_URL}${endpoint}" || true)"

  if [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
    printf -v "$status_var" '%s' "ok"
  else
    printf -v "$status_var" '%s' "error"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  printf -v "$code_var" '%s' "$http_code"
}

HEALTH_STATUS="error"
HEALTH_HTTP_CODE="000"
QUEUE_STATUS="error"
QUEUE_HTTP_CODE="000"

fetch_endpoint "/v1/health" "$HEALTH_BODY_FILE" HEALTH_STATUS HEALTH_HTTP_CODE
fetch_endpoint "/v1/ingest/queue/status" "$QUEUE_BODY_FILE" QUEUE_STATUS QUEUE_HTTP_CODE

cat > "$HEALTH_FILE" <<EOF
{
  "run_ts": "$RUN_TS",
  "window_id": "$WINDOW_ID",
  "edge_pid": "$EDGE_PID",
  "base_url": "$BASE_URL",
  "snapshots": [
    {
      "endpoint": "/v1/health",
      "status": "$HEALTH_STATUS",
      "http_code": "$HEALTH_HTTP_CODE",
      "body_file": "$(basename "$HEALTH_BODY_FILE")"
    },
    {
      "endpoint": "/v1/ingest/queue/status",
      "status": "$QUEUE_STATUS",
      "http_code": "$QUEUE_HTTP_CODE",
      "body_file": "$(basename "$QUEUE_BODY_FILE")"
    }
  ]
}
EOF

cat > "$METRICS_FILE" <<EOF
{
  "run_ts": "$RUN_TS",
  "window_id": "$WINDOW_ID",
  "edge_pid": "$EDGE_PID",
  "git_rev": "$GIT_REV",
  "checks": {
    "trigger_coverage_pytest": "$TRIGGER_TEST_STATUS",
    "debounce_pytest": "$DEBOUNCE_TEST_STATUS",
    "health_snapshot": "$HEALTH_STATUS",
    "queue_snapshot": "$QUEUE_STATUS"
  },
  "metrics": {
    "trigger_coverage": null,
    "debounce_violations": null,
    "capture_latency_p50": null,
    "capture_latency_p90": null,
    "capture_latency_p95": null,
    "capture_latency_p99": null,
    "collapse_trigger_count": null,
    "queue_saturation_ratio": null,
    "overflow_drop_count": null
  },
  "note": "Populate metrics from SQL/collector outputs for final acceptance evidence."
}
EOF

cat > "$UI_PROOF_FILE" <<EOF
# P1-S2a UI Evidence Index

- run_ts: $RUN_TS
- window_id: $WINDOW_ID
- edge_pid: $EDGE_PID
- base_url: $BASE_URL

## Required Proof Items

1. Grid ('/') status visibility proof
   - Capture upload in progress
   - Enqueued / completed status visible
2. Timeline ('/timeline') new frame visibility proof
3. Timeline timestamp定位 proof

## Attachments

- Add screenshot/log references below:
  - [ ] Grid evidence path:
  - [ ] Timeline new-frame evidence path:
  - [ ] Timeline定位 evidence path:
  - [ ] Additional notes:
EOF

if [[ "$FAIL_COUNT" -eq 0 ]]; then
  RESULT="Pass"
  EXIT_CODE=0
else
  RESULT="Fail"
  EXIT_CODE=1
fi

echo "[INFO] Result: $RESULT"
echo "[INFO] Evidence files:"
echo "  - $LOG_FILE"
echo "  - $METRICS_FILE"
echo "  - $HEALTH_FILE"
echo "  - $UI_PROOF_FILE"
echo "[INFO] Finished"

exit "$EXIT_CODE"
