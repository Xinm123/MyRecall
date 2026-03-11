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
  --edge-db PATH         Override edge.db path
  --sample-seconds N     1Hz sampling window for queue/health snapshots (default: 5)
  --skip-pytest          Skip pytest checks (still produce evidence files)
  -h, --help             Show this help and exit

Outputs:
  - p1-s2a-local-gate.log
  - p1-s2a-metrics.json
  - p1-s2a-health-snapshots.json
  - p1-s2a-ui-proof.md
  - p1-s2a-trigger-channel-raw.jsonl
EOF
}

BASE_URL="http://localhost:${OPENRECALL_PORT:-8083}"
EVIDENCE_DIR="docs/v3/acceptance/phase1/evidence"
WINDOW_ID=""
EDGE_PID=""
EDGE_DB=""
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
    --edge-db)
      EDGE_DB="$2"
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
WINDOW_ID="${WINDOW_ID:-p1-s2a-${RUN_TAG}}"
EDGE_PID="${EDGE_PID:-unknown}"
EDGE_DB="${EDGE_DB:-${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db}"
GIT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
HOSTNAME_VAL="$(hostname 2>/dev/null || echo unknown-host)"

LOG_FILE="$EVIDENCE_DIR/p1-s2a-local-gate.log"
METRICS_FILE="$EVIDENCE_DIR/p1-s2a-metrics.json"
HEALTH_FILE="$EVIDENCE_DIR/p1-s2a-health-snapshots.json"
UI_PROOF_FILE="$EVIDENCE_DIR/p1-s2a-ui-proof.md"
TRIGGER_RAW_FILE="$EVIDENCE_DIR/p1-s2a-trigger-channel-raw.jsonl"

HEALTH_BODY_FILE="$EVIDENCE_DIR/p1-s2a-health-response.json"
QUEUE_BODY_FILE="$EVIDENCE_DIR/p1-s2a-queue-response.json"
SAMPLER_SUMMARY_FILE="$EVIDENCE_DIR/.p1-s2a-sampler-summary.json"

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] P1-S2a local gate started"
echo "[INFO] run_ts=$RUN_TS"
echo "[INFO] window_id=$WINDOW_ID"
echo "[INFO] edge_pid=$EDGE_PID"
echo "[INFO] base_url=$BASE_URL"
echo "[INFO] evidence_dir=$EVIDENCE_DIR"
echo "[INFO] edge_db=$EDGE_DB"
echo "[INFO] sample_seconds=$SAMPLE_SECONDS"
echo "[INFO] git_rev=$GIT_REV"
echo "[INFO] hostname=$HOSTNAME_VAL"

FAIL_COUNT=0
TRIGGER_TEST_STATUS="not_run"
DEBOUNCE_TEST_STATUS="not_run"
DEVICE_BINDING_TEST_STATUS="not_run"
SERVER_CONTRACT_STATUS="not_run"

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
  DEVICE_BINDING_TEST_STATUS="skipped"
  SERVER_CONTRACT_STATUS="skipped"
else
  run_pytest_check "tests/test_p1_s2a_trigger_coverage.py" TRIGGER_TEST_STATUS
  run_pytest_check "tests/test_p1_s2a_debounce.py" DEBOUNCE_TEST_STATUS
  run_pytest_check "tests/test_p1_s2a_device_binding.py" DEVICE_BINDING_TEST_STATUS
  run_pytest_check "tests/test_p1_s2a_server_contracts.py" SERVER_CONTRACT_STATUS
fi

python3 - "$BASE_URL" "$SAMPLE_SECONDS" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$HEALTH_FILE" "$TRIGGER_RAW_FILE" "$HEALTH_BODY_FILE" "$QUEUE_BODY_FILE" "$SAMPLER_SUMMARY_FILE" <<'PY'
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_json(base_url: str, endpoint: str) -> tuple[str, int, object | None, str]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    try:
        with request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
            status_code = response.getcode()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            status = "ok" if 200 <= status_code < 300 else "error"
            return status, status_code, payload, body
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        return "error", exc.code, payload, body
    except Exception:
        return "error", 0, None, ""


base_url = sys.argv[1]
sample_seconds = max(1, int(sys.argv[2]))
run_ts = sys.argv[3]
window_id = sys.argv[4]
edge_pid = sys.argv[5]
health_path = Path(sys.argv[6])
raw_path = Path(sys.argv[7])
health_body_path = Path(sys.argv[8])
queue_body_path = Path(sys.argv[9])
summary_path = Path(sys.argv[10])

snapshots: list[dict[str, object]] = []
queue_samples: list[dict[str, object]] = []
latest_health_body = ""
latest_queue_body = ""
latest_health_status = "error"
latest_queue_status = "error"
latest_health_code = 0
latest_queue_code = 0

for index in range(sample_seconds):
    sample_ts = utc_now_iso()
    health_status, health_code, health_payload, health_body = fetch_json(base_url, "/v1/health")
    queue_status, queue_code, queue_payload, queue_body = fetch_json(base_url, "/v1/ingest/queue/status")

    latest_health_status = health_status
    latest_queue_status = queue_status
    latest_health_code = health_code
    latest_queue_code = queue_code
    latest_health_body = health_body
    latest_queue_body = queue_body

    snapshots.append(
        {
            "ts": sample_ts,
            "endpoint": "/v1/health",
            "status": health_status,
            "http_code": health_code,
            "body_file": health_body_path.name,
        }
    )
    snapshots.append(
        {
            "ts": sample_ts,
            "endpoint": "/v1/ingest/queue/status",
            "status": queue_status,
            "http_code": queue_code,
            "body_file": queue_body_path.name,
        }
    )

    trigger_channel: dict[str, object] = {}
    if isinstance(queue_payload, dict):
        candidate = queue_payload.get("trigger_channel")
        if isinstance(candidate, dict):
            trigger_channel = candidate

    queue_samples.append(
        {
            "ts": sample_ts,
            "queue_depth": int(trigger_channel.get("queue_depth", 0) or 0),
            "queue_capacity": int(trigger_channel.get("queue_capacity", 0) or 0),
            "collapse_trigger_count": int(trigger_channel.get("collapse_trigger_count", 0) or 0),
            "overflow_drop_count": int(trigger_channel.get("overflow_drop_count", 0) or 0),
            "status": queue_status,
        }
    )

    if index < sample_seconds - 1:
        time.sleep(1)

health_body_path.write_text(latest_health_body if latest_health_body else "{}")
queue_body_path.write_text(latest_queue_body if latest_queue_body else "{}")
raw_path.write_text("".join(json.dumps(sample) + "\n" for sample in queue_samples))
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
summary_path.write_text(
    json.dumps(
        {
            "health_status": latest_health_status,
            "health_http_code": latest_health_code,
            "queue_status": latest_queue_status,
            "queue_http_code": latest_queue_code,
        },
        indent=2,
    )
)
PY

HEALTH_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["health_status"])' "$SAMPLER_SUMMARY_FILE")"
HEALTH_HTTP_CODE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["health_http_code"])' "$SAMPLER_SUMMARY_FILE")"
QUEUE_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["queue_status"])' "$SAMPLER_SUMMARY_FILE")"
QUEUE_HTTP_CODE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["queue_http_code"])' "$SAMPLER_SUMMARY_FILE")"

if [[ "$HEALTH_STATUS" != "ok" ]]; then
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi
if [[ "$QUEUE_STATUS" != "ok" ]]; then
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

python3 - "$EDGE_DB" "$TRIGGER_RAW_FILE" "$SAMPLER_SUMMARY_FILE" "$METRICS_FILE" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$GIT_REV" "$BASE_URL" "$TRIGGER_TEST_STATUS" "$DEBOUNCE_TEST_STATUS" "$DEVICE_BINDING_TEST_STATUS" "$SERVER_CONTRACT_STATUS" "$EVIDENCE_DIR/p1-s2a-loss-rate-summary.json" <<'PY'
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    normalized = raw.strip().replace(" ", "T")
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    elif "+" not in normalized and "-" not in normalized[10:]:
        normalized = f"{normalized}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


edge_db = Path(sys.argv[1])
raw_path = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
metrics_path = Path(sys.argv[4])
run_ts = sys.argv[5]
window_id = sys.argv[6]
edge_pid = sys.argv[7]
git_rev = sys.argv[8]
base_url = sys.argv[9]
trigger_test_status = sys.argv[10]
debounce_test_status = sys.argv[11]
device_binding_status = sys.argv[12]
server_contract_status = sys.argv[13]
loss_rate_summary_path = Path(sys.argv[14])

allowed_triggers = ("idle", "app_switch", "manual", "click")
trigger_counts: Counter[str] = Counter({trigger: 0 for trigger in allowed_triggers})
trigger_coverage = None
capture_latency_values: list[float] = []
capture_latency_anomaly_count = 0
db_available = edge_db.exists()

if db_available:
    with sqlite3.connect(str(edge_db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT capture_trigger, device_name, event_ts, ingested_at
            FROM frames
            ORDER BY id ASC
            """
        ).fetchall()

    if rows:
        covered = 0
        for row in rows:
            trigger = row["capture_trigger"]
            device_name = row["device_name"]
            event_ts = row["event_ts"]
            if trigger in allowed_triggers and device_name and event_ts:
                covered += 1
                trigger_counts[str(trigger)] += 1
            ingested_at_dt = parse_utc(row["ingested_at"])
            event_ts_dt = parse_utc(event_ts)
            if ingested_at_dt is None or event_ts_dt is None:
                capture_latency_anomaly_count += 1
                continue
            latency_ms = (ingested_at_dt - event_ts_dt).total_seconds() * 1000.0
            if latency_ms < 0:
                capture_latency_anomaly_count += 1
                continue
            capture_latency_values.append(latency_ms)
        trigger_coverage = (covered / len(rows)) * 100.0

queue_samples = []
if raw_path.exists():
    for line in raw_path.read_text().splitlines():
        if line.strip():
            queue_samples.append(json.loads(line))

valid_queue_samples = [
    sample
    for sample in queue_samples
    if sample.get("status") == "ok" and int(sample.get("queue_capacity", 0) or 0) > 0
]
if valid_queue_samples:
    saturated = sum(
        1
        for sample in valid_queue_samples
        if int(sample["queue_depth"]) >= 0.9 * int(sample["queue_capacity"])
    )
    queue_saturation_ratio = (saturated / len(valid_queue_samples)) * 100.0
    collapse_trigger_count = max(int(sample["collapse_trigger_count"]) for sample in valid_queue_samples)
    overflow_drop_count = max(int(sample["overflow_drop_count"]) for sample in valid_queue_samples)
else:
    queue_saturation_ratio = 0.0
    collapse_trigger_count = 0
    overflow_drop_count = 0

summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
loss_rate_summary = (
    json.loads(loss_rate_summary_path.read_text())
    if loss_rate_summary_path.exists()
    else {}
)
broken_window = (
    summary.get("health_status") != "ok"
    or summary.get("queue_status") != "ok"
    or not db_available
    or not valid_queue_samples
)

metrics_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "edge_pid": edge_pid,
            "broken_window": broken_window,
            "git_rev": git_rev,
            "checks": {
                "trigger_coverage_pytest": trigger_test_status,
                "debounce_pytest": debounce_test_status,
                "device_binding_pytest": device_binding_status,
                "server_contracts_pytest": server_contract_status,
                "health_snapshot": summary.get("health_status", "error"),
                "queue_snapshot": summary.get("queue_status", "error"),
                "db_metrics": "ok" if db_available else "missing",
            },
            "metrics": {
                "trigger_coverage": trigger_coverage,
                "trigger_counts": {trigger: trigger_counts[trigger] for trigger in allowed_triggers},
                "capture_latency_p50": percentile(capture_latency_values, 0.50),
                "capture_latency_p90": percentile(capture_latency_values, 0.90),
                "capture_latency_p95": percentile(capture_latency_values, 0.95),
                "capture_latency_p99": percentile(capture_latency_values, 0.99),
                "capture_latency_sample_count": len(capture_latency_values),
                "capture_latency_anomaly_count": capture_latency_anomaly_count,
                "collapse_trigger_count": collapse_trigger_count,
                "queue_saturation_ratio": queue_saturation_ratio,
                "overflow_drop_count": overflow_drop_count,
                "loss_rate": loss_rate_summary.get("loss_rate"),
            },
            "context": {
                "base_url": base_url,
                "edge_db": str(edge_db),
                "raw_trigger_channel_file": raw_path.name,
                "loss_rate_summary_file": loss_rate_summary_path.name,
                "loss_rate_injected_event_count": loss_rate_summary.get("injected_event_count"),
                "loss_rate_produced_capture_count": loss_rate_summary.get("produced_capture_count"),
                "loss_rate_committed_capture_count": loss_rate_summary.get("committed_capture_count"),
                "loss_rate_calculation_basis": loss_rate_summary.get("calculation_basis"),
            },
        },
        indent=2,
    )
)
PY

cat > "$UI_PROOF_FILE" <<EOF
# P1-S2a UI Evidence Index

- run_ts: $RUN_TS
- window_id: $WINDOW_ID
- edge_pid: $EDGE_PID
- base_url: $BASE_URL
- health_snapshots: $(basename "$HEALTH_FILE")
- raw_trigger_channel: $(basename "$TRIGGER_RAW_FILE")

## Required Proof Items

1. Grid ('/') status visibility proof
   - Capture upload in progress
   - Enqueued / completed status visible
2. Timeline ('/timeline') new frame visibility proof
3. Timeline timestamp定位 proof
4. Health anchor (#mr-health) proof

## Attachments

- Add screenshot/log references below:
  - [ ] Grid evidence path:
  - [ ] Timeline new-frame evidence path:
  - [ ] Timeline定位 evidence path:
  - [ ] Health anchor evidence path:
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
echo "  - $TRIGGER_RAW_FILE"
echo "[INFO] Finished"

rm -f "$SAMPLER_SUMMARY_FILE"

exit "$EXIT_CODE"
