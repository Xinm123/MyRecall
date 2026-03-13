#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: p1_s2a_plus_local.sh [options]

Run local P1-S2a+ permission stability checks and produce the required evidence bundle.

Prerequisite:
  - Start server first in another terminal: ./run_server.sh --debug
  - Verify health endpoint is reachable before running this script
    (for example: curl http://localhost:${OPENRECALL_PORT:-8083}/v1/health)

Options:
  --base-url URL         Edge base URL (default: http://localhost:${OPENRECALL_PORT:-8083})
  --evidence-dir DIR     Evidence output directory
                         (default: docs/v3/acceptance/phase1/evidence)
  --window-id ID         Custom window_id for this run
  --edge-pid PID         Edge process id for metadata (optional)
  --sample-seconds N     1Hz sampling window for permission/health snapshots (default: 5)
  --skip-pytest          Skip pytest checks (still produce evidence files)
  -h, --help             Show this help and exit

Outputs:
  - p1-s2a-plus-local-gate.log
  - p1-s2a-plus-permission-transitions.jsonl
  - p1-s2a-plus-health-snapshots.json
  - p1-s2a-plus-ui-proof.md
  - p1-s2a-plus-context.json
EOF
}

BASE_URL="http://localhost:${OPENRECALL_PORT:-8083}"
EVIDENCE_DIR="docs/v3/acceptance/phase1/evidence"
WINDOW_ID=""
EDGE_PID=""
SAMPLE_SECONDS=5
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
    --sample-seconds)
      SAMPLE_SECONDS="$2"
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
WINDOW_ID="${WINDOW_ID:-p1-s2a-plus-${RUN_TAG}}"
EDGE_PID="${EDGE_PID:-unknown}"
GIT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

LOG_FILE="$EVIDENCE_DIR/p1-s2a-plus-local-gate.log"
TRANSITIONS_FILE="$EVIDENCE_DIR/p1-s2a-plus-permission-transitions.jsonl"
HEALTH_FILE="$EVIDENCE_DIR/p1-s2a-plus-health-snapshots.json"
UI_PROOF_FILE="$EVIDENCE_DIR/p1-s2a-plus-ui-proof.md"
CONTEXT_FILE="$EVIDENCE_DIR/p1-s2a-plus-context.json"
SAMPLER_SUMMARY_FILE="$EVIDENCE_DIR/.p1-s2a-plus-sampler-summary.json"

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] P1-S2a+ local gate started"
echo "[INFO] run_ts=$RUN_TS"
echo "[INFO] window_id=$WINDOW_ID"
echo "[INFO] edge_pid=$EDGE_PID"
echo "[INFO] base_url=$BASE_URL"
echo "[INFO] evidence_dir=$EVIDENCE_DIR"
echo "[INFO] sample_seconds=$SAMPLE_SECONDS"
echo "[INFO] git_rev=$GIT_REV"

FAIL_COUNT=0
PERMISSION_SUITE_STATUS="not_run"

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
  PERMISSION_SUITE_STATUS="skipped"
else
  run_pytest_check "tests/test_p1_s2a_plus_permission_fsm.py" PERMISSION_SUITE_STATUS
fi

python3 - "$BASE_URL" "$SAMPLE_SECONDS" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$HEALTH_FILE" "$TRANSITIONS_FILE" "$SAMPLER_SUMMARY_FILE" <<'PY'
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_json(base_url: str, endpoint: str) -> tuple[str, int, object | None]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    try:
        with request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            status = "ok" if 200 <= response.getcode() < 300 else "error"
            return status, response.getcode(), payload
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        return "error", exc.code, payload
    except Exception:
        return "error", 0, None


base_url = sys.argv[1]
sample_seconds = max(1, int(sys.argv[2]))
run_ts = sys.argv[3]
window_id = sys.argv[4]
edge_pid = sys.argv[5]
health_path = Path(sys.argv[6])
transitions_path = Path(sys.argv[7])
summary_path = Path(sys.argv[8])

snapshots: list[dict[str, object]] = []
transitions: list[dict[str, object]] = []
latest_health_status = "error"
latest_http_code = 0

for index in range(sample_seconds):
    sample_ts = utc_now_iso()
    request_status, http_code, payload = fetch_json(base_url, "/v1/health")
    permission_status = "unknown"
    permission_reason = "unknown"
    health_status = "error"

    if isinstance(payload, dict):
        permission_status = str(payload.get("capture_permission_status") or permission_status)
        permission_reason = str(payload.get("capture_permission_reason") or permission_reason)
        health_status = str(payload.get("status") or health_status)

    latest_health_status = health_status if request_status == "ok" else request_status
    latest_http_code = http_code

    snapshots.append(
        {
            "ts": sample_ts,
            "endpoint": "/v1/health",
            "status": request_status,
            "http_code": http_code,
            "capture_permission_status": permission_status,
            "capture_permission_reason": permission_reason,
            "health_status": health_status,
        }
    )
    transitions.append(
        {
            "ts": sample_ts,
            "capture_permission_status": permission_status,
            "capture_permission_reason": permission_reason,
            "health_status": health_status,
            "http_code": http_code,
        }
    )

    if index < sample_seconds - 1:
        time.sleep(1)

health_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "edge_pid": edge_pid,
            "snapshots": snapshots,
        },
        indent=2,
    )
)
transitions_path.write_text(
    "".join(json.dumps(transition) + "\n" for transition in transitions)
)
summary_path.write_text(
    json.dumps(
        {
            "health_status": latest_health_status,
            "health_http_code": latest_http_code,
        },
        indent=2,
    )
)
PY

HEALTH_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["health_status"])' "$SAMPLER_SUMMARY_FILE")"
HEALTH_HTTP_CODE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["health_http_code"])' "$SAMPLER_SUMMARY_FILE")"

if [[ "$HEALTH_STATUS" != "ok" ]]; then
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

python3 - "$CONTEXT_FILE" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$GIT_REV" "$BASE_URL" "$SAMPLE_SECONDS" "$PERMISSION_SUITE_STATUS" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


context_path = Path(sys.argv[1])
run_ts = sys.argv[2]
window_id = sys.argv[3]
edge_pid = sys.argv[4]
git_rev = sys.argv[5]
base_url = sys.argv[6]
sample_seconds = int(sys.argv[7])
permission_suite_status = sys.argv[8]

permission_env_keys = [
    "OPENRECALL_PERMISSION_POLL_INTERVAL_SEC",
    "OPENRECALL_MIN_CAPTURE_INTERVAL_MS",
    "OPENRECALL_IDLE_CAPTURE_INTERVAL_MS",
    "OPENRECALL_SKIP_PERMISSION_CHECK",
    "OPENRECALL_PORT",
]

context_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "edge_pid": edge_pid,
            "git_rev": git_rev,
            "terminal_mode": "Terminal mode",
            "base_url": base_url,
            "execution_window": {
                "run_ts": run_ts,
                "completed_at": datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "sample_seconds": sample_seconds,
            },
            "permission_suite_status": permission_suite_status,
            "permission_env": {
                key: os.environ.get(key) for key in permission_env_keys
            },
        },
        indent=2,
    )
)
PY

cat > "$UI_PROOF_FILE" <<EOF
# P1-S2a+ UI Evidence Index

- run_ts: $RUN_TS
- window_id: $WINDOW_ID
- edge_pid: $EDGE_PID
- base_url: $BASE_URL
- health_snapshots: $(basename "$HEALTH_FILE")
- permission_transitions: $(basename "$TRANSITIONS_FILE")

## Required Scenario Proof

1. startup_not_determined
   - [ ] health snapshot
   - [ ] UI guidance proof
   - [ ] log reference
2. startup_denied
   - [ ] health snapshot
   - [ ] degraded UI proof
   - [ ] log reference
3. revoked_mid_run
   - [ ] permission timeline proof
   - [ ] degraded health proof
   - [ ] capture-stop proof
4. restored_after_denied
   - [ ] recovering health proof
   - [ ] granted recovery proof
   - [ ] no-restart proof
5. stale_permission_state
   - [ ] stale health proof
   - [ ] degraded UI proof
   - [ ] log reference
EOF

if [[ "$FAIL_COUNT" -eq 0 ]]; then
  RESULT="Pass"
  EXIT_CODE=0
else
  RESULT="Fail"
  EXIT_CODE=1
fi

echo "[INFO] health_status=$HEALTH_STATUS http_code=$HEALTH_HTTP_CODE"
echo "[INFO] permission_suite_status=$PERMISSION_SUITE_STATUS"
echo "[INFO] Result: $RESULT"
echo "[INFO] Evidence files:"
echo "  - $LOG_FILE"
echo "  - $TRANSITIONS_FILE"
echo "  - $HEALTH_FILE"
echo "  - $UI_PROOF_FILE"
echo "  - $CONTEXT_FILE"

rm -f "$SAMPLER_SUMMARY_FILE"

exit "$EXIT_CODE"
