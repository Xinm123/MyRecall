#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: p1_s2b_local.sh [options]

Run local P1-S2b gate checks and produce a standard evidence bundle.

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
  - p1-s2b-local-gate.log
  - p1-s2b-metrics.json
  - p1-s2b-health-snapshots.json
  - p1-s2b-outcomes.json
  - p1-s2b-proof-filter.json
  - p1-s2b-ui-proof.md
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
WINDOW_ID="${WINDOW_ID:-p1-s2b-${RUN_TAG}}"
EDGE_PID="${EDGE_PID:-unknown}"
EDGE_DB="${EDGE_DB:-${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db}"
HOST_PID="$$"
GIT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
HOSTNAME_VAL="$(hostname 2>/dev/null || echo unknown-host)"

LOG_FILE="$EVIDENCE_DIR/p1-s2b-local-gate.log"
METRICS_FILE="$EVIDENCE_DIR/p1-s2b-metrics.json"
HEALTH_FILE="$EVIDENCE_DIR/p1-s2b-health-snapshots.json"
OUTCOMES_FILE="$EVIDENCE_DIR/p1-s2b-outcomes.json"
PROOF_FILTER_FILE="$EVIDENCE_DIR/p1-s2b-proof-filter.json"
UI_PROOF_FILE="$EVIDENCE_DIR/p1-s2b-ui-proof.md"
CAPTURE_ATTEMPTS_FILE="$EVIDENCE_DIR/.p1-s2b-capture-attempts.jsonl"
INGEST_DECISIONS_FILE="$EVIDENCE_DIR/.p1-s2b-ingest-decisions.jsonl"

HEALTH_BODY_FILE="$EVIDENCE_DIR/.p1-s2b-health-response.json"
QUEUE_BODY_FILE="$EVIDENCE_DIR/.p1-s2b-queue-response.json"
SAMPLER_SUMMARY_FILE="$EVIDENCE_DIR/.p1-s2b-sampler-summary.json"

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] P1-S2b local gate started"
echo "[INFO] run_ts=$RUN_TS"
echo "[INFO] window_id=$WINDOW_ID"
echo "[INFO] edge_pid=$EDGE_PID"
echo "[INFO] host_pid=$HOST_PID"
echo "[INFO] base_url=$BASE_URL"
echo "[INFO] evidence_dir=$EVIDENCE_DIR"
echo "[INFO] edge_db=$EDGE_DB"
echo "[INFO] sample_seconds=$SAMPLE_SECONDS"
echo "[INFO] git_rev=$GIT_REV"
echo "[INFO] hostname=$HOSTNAME_VAL"

FAIL_COUNT=0
CONTENT_HASH_STATUS="not_run"
AX_TIMEOUT_STATUS="not_run"
FOCUSED_CONTEXT_STATUS="not_run"
DEVICE_BINDING_STATUS="not_run"
BROWSER_URL_STATUS="not_run"
PERMISSION_RECOVERY_STATUS="not_run"

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
  CONTENT_HASH_STATUS="skipped"
  AX_TIMEOUT_STATUS="skipped"
  FOCUSED_CONTEXT_STATUS="skipped"
  DEVICE_BINDING_STATUS="skipped"
  BROWSER_URL_STATUS="skipped"
  PERMISSION_RECOVERY_STATUS="skipped"
else
  run_pytest_check "tests/test_p1_s2b_content_hash.py" CONTENT_HASH_STATUS
  run_pytest_check "tests/test_p1_s2b_ax_timeout.py" AX_TIMEOUT_STATUS
  run_pytest_check "tests/test_p1_s2b_focused_context.py" FOCUSED_CONTEXT_STATUS
  run_pytest_check "tests/test_p1_s2b_device_binding.py" DEVICE_BINDING_STATUS
  run_pytest_check "tests/test_p1_s2b_browser_url.py" BROWSER_URL_STATUS
  run_pytest_check "tests/test_p1_s2b_permission_recovery.py" PERMISSION_RECOVERY_STATUS
fi

python3 - "$BASE_URL" "$SAMPLE_SECONDS" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$HEALTH_FILE" "$HEALTH_BODY_FILE" "$QUEUE_BODY_FILE" "$SAMPLER_SUMMARY_FILE" <<'PY'
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
health_body_path = Path(sys.argv[7])
queue_body_path = Path(sys.argv[8])
summary_path = Path(sys.argv[9])

snapshots: list[dict[str, object]] = []
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

    for endpoint, status, code, payload, body_file in (
        ("/v1/health", health_status, health_code, health_payload, health_body_path.name),
        ("/v1/ingest/queue/status", queue_status, queue_code, queue_payload, queue_body_path.name),
    ):
        entry: dict[str, object] = {
            "ts": sample_ts,
            "endpoint": endpoint,
            "status": status,
            "http_code": code,
            "body_file": body_file,
        }
        if isinstance(payload, dict):
            for key in (
                "capture_permission_status",
                "capture_permission_reason",
                "screen_capture_status",
                "screen_capture_reason",
            ):
                if key in payload:
                    entry[key] = payload[key]
        snapshots.append(entry)

    if index < sample_seconds - 1:
        time.sleep(1)

health_body_path.write_text(latest_health_body if latest_health_body else "{}")
queue_body_path.write_text(latest_queue_body if latest_queue_body else "{}")
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
QUEUE_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["queue_status"])' "$SAMPLER_SUMMARY_FILE")"

if [[ "$HEALTH_STATUS" != "ok" ]]; then
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi
if [[ "$QUEUE_STATUS" != "ok" ]]; then
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

python3 - "$EDGE_DB" "$METRICS_FILE" "$OUTCOMES_FILE" "$PROOF_FILTER_FILE" "$SAMPLER_SUMMARY_FILE" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$HOST_PID" "$GIT_REV" "$BASE_URL" "$HEALTH_FILE" "$CAPTURE_ATTEMPTS_FILE" "$INGEST_DECISIONS_FILE" "$CONTENT_HASH_STATUS" "$AX_TIMEOUT_STATUS" "$FOCUSED_CONTEXT_STATUS" "$DEVICE_BINDING_STATUS" "$BROWSER_URL_STATUS" "$PERMISSION_RECOVERY_STATUS" <<'PY'
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
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
metrics_path = Path(sys.argv[2])
outcomes_path = Path(sys.argv[3])
proof_filter_path = Path(sys.argv[4])
summary_path = Path(sys.argv[5])
run_ts = sys.argv[6]
window_id = sys.argv[7]
edge_pid = sys.argv[8]
host_pid = sys.argv[9]
git_rev = sys.argv[10]
base_url = sys.argv[11]
health_file = Path(sys.argv[12])
capture_attempts_path = Path(sys.argv[13])
ingest_decisions_path = Path(sys.argv[14])
content_hash_status = sys.argv[15]
ax_timeout_status = sys.argv[16]
focused_context_status = sys.argv[17]
device_binding_status = sys.argv[18]
browser_url_status = sys.argv[19]
permission_recovery_status = sys.argv[20]


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records

summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
db_available = edge_db.exists()
capture_attempts = load_jsonl(capture_attempts_path)
ingest_decisions = load_jsonl(ingest_decisions_path)
ingest_by_capture_id = {
    str(record.get("capture_id")): record
    for record in ingest_decisions
    if record.get("capture_id") is not None
}

restart_events: list[dict[str, object]] = []


def append_restart_events(records: list[dict[str, object]], pid_key: str, source: str) -> None:
    previous_pid: object | None = None
    for index, record in enumerate(records):
        pid = record.get(pid_key)
        if pid is None:
            continue
        if previous_pid is None:
            previous_pid = pid
            continue
        if pid != previous_pid:
            restart_events.append(
                {
                    "source": source,
                    "index": index,
                    "from_pid": previous_pid,
                    "to_pid": pid,
                }
            )
            previous_pid = pid


append_restart_events(capture_attempts, "host_pid", "host")
append_restart_events(ingest_decisions, "edge_pid", "edge")
broken_window = bool(restart_events) or not db_available

rows: list[sqlite3.Row] = []
if db_available:
    with sqlite3.connect(str(edge_db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, capture_id, timestamp, app_name, window_name, browser_url,
                   device_name, capture_trigger, event_ts, ingested_at,
                   accessibility_text, content_hash
            FROM frames
            ORDER BY id ASC
            """
        ).fetchall()

required_browser_apps = {"Google Chrome", "Safari", "Microsoft Edge"}
browser_url_counts: Counter[str] = Counter(
    {
        "browser_url_success": 0,
        "browser_url_rejected_stale": 0,
        "browser_url_failed_all_tiers": 0,
        "browser_url_skipped": 0,
    }
)
outcome_counts: Counter[str] = Counter(
    {
        "capture_completed": 0,
        "ax_empty": 0,
        "ax_timeout_partial": 0,
        "browser_url_rejected_stale": 0,
        "permission_blocked": 0,
        "dedup_skipped": 0,
        "spool_failed": 0,
        "schema_rejected": 0,
    }
)
capture_latency_values: list[float] = []
capture_latency_anomaly_count = 0
inter_write_by_device: dict[str, list[float]] = defaultdict(list)
focused_context_mismatch_count = 0
attempts: list[dict[str, object]] = []
ax_hash_eligible = 0
content_hash_present_count = 0

if capture_attempts:
    for record in capture_attempts:
        outcome = str(record.get("outcome") or "capture_completed")
        if outcome in outcome_counts:
            outcome_counts[outcome] += 1

    for record in ingest_decisions:
        decision = record.get("decision")
        if decision == "schema_rejected":
            outcome_counts["schema_rejected"] += 1

    for record in capture_attempts:
        capture_id = str(record.get("capture_id") or "")
        final_device_name = record.get("final_device_name")
        ingest_record = ingest_by_capture_id.get(capture_id, {})
        decision = ingest_record.get("decision")
        host_schema_version = record.get("host_schema_version")
        edge_schema_version = ingest_record.get("edge_schema_version")
        exclusion_reason = None
        if broken_window:
            exclusion_reason = "broken_window"
        elif record.get("alias_only_payload") is True:
            exclusion_reason = "alias_only_payload"
        elif record.get("missing_canonical_keys") is True:
            exclusion_reason = "missing_canonical_keys"
        elif not final_device_name:
            exclusion_reason = "final_device_name_missing"
        elif record.get("final_device_name_mismatch") is True:
            exclusion_reason = "final_device_name_mismatch"
        elif (
            host_schema_version is not None
            and edge_schema_version is not None
            and host_schema_version != edge_schema_version
        ):
            exclusion_reason = "mixed_version"
        elif decision == "schema_rejected":
            exclusion_reason = "schema_rejected"
        elif decision == "queue_rejected":
            exclusion_reason = "queue_rejected"

        proof_status = "excluded" if exclusion_reason else "included"
        metric_eligibility: list[str] = []
        outcome = str(record.get("outcome") or "capture_completed")
        if proof_status == "included":
            if outcome in {"capture_completed", "ax_timeout_partial"}:
                metric_eligibility.append("content_hash_coverage")
            if final_device_name and inter_write_by_device.get(str(final_device_name)):
                metric_eligibility.append("inter_write_gap_sec")

        attempts.append(
            {
                "capture_id": capture_id,
                "frame_id": ingest_record.get("frame_id"),
                "outcome": outcome,
                "proof_status": proof_status,
                "exclusion_reason": exclusion_reason,
                "metric_eligibility": metric_eligibility,
                "final_device_name": final_device_name,
            }
        )
else:
    for row in rows:
        accessibility_text = (row["accessibility_text"] or "") if row["accessibility_text"] is not None else ""
        content_hash = row["content_hash"]
        app_name = row["app_name"]
        window_name = row["window_name"]
        browser_url = row["browser_url"]
        device_name = row["device_name"]

        if accessibility_text.strip() and content_hash:
            outcome = "capture_completed"
        elif not accessibility_text.strip() and content_hash is None:
            outcome = "ax_empty"
        else:
            outcome = "capture_completed"
        outcome_counts[outcome] += 1

        exclusion_reason = None
        proof_status = "included"
        if broken_window:
            proof_status = "excluded"
            exclusion_reason = "broken_window"
        elif not device_name:
            proof_status = "excluded"
            exclusion_reason = "final_device_name_missing"
        elif not app_name and not window_name and not browser_url:
            proof_status = "excluded"
            exclusion_reason = "missing_canonical_keys"

        metric_eligibility: list[str] = []
        if proof_status == "included":
            if accessibility_text.strip():
                metric_eligibility.append("content_hash_coverage")
            if device_name and inter_write_by_device.get(device_name):
                metric_eligibility.append("inter_write_gap_sec")
            if app_name in required_browser_apps:
                metric_eligibility.append("browser_url_required_success")

        attempts.append(
            {
                "capture_id": row["capture_id"],
                "frame_id": row["id"],
                "outcome": outcome,
                "proof_status": proof_status,
                "exclusion_reason": exclusion_reason,
                "metric_eligibility": metric_eligibility,
                "final_device_name": device_name,
            }
        )

metric_rows = rows
if capture_attempts:
    included_capture_ids = {
        str(attempt["capture_id"])
        for attempt in attempts
        if attempt["proof_status"] == "included"
    }
    metric_rows = [
        row for row in rows if str(row["capture_id"]) in included_capture_ids
    ]

browser_url_counts = Counter(
    {
        "browser_url_success": 0,
        "browser_url_rejected_stale": 0,
        "browser_url_failed_all_tiers": 0,
        "browser_url_skipped": 0,
    }
)
capture_latency_values = []
capture_latency_anomaly_count = 0
inter_write_by_device = defaultdict(list)
focused_context_mismatch_count = 0
ax_hash_eligible = 0
content_hash_present_count = 0
device_last_ingested: dict[str, datetime] = {}

for row in metric_rows:
    accessibility_text = (row["accessibility_text"] or "") if row["accessibility_text"] is not None else ""
    content_hash = row["content_hash"]
    app_name = row["app_name"]
    window_name = row["window_name"]
    browser_url = row["browser_url"]
    device_name = row["device_name"]
    event_ts = parse_utc(row["event_ts"])
    ingested_at = parse_utc(row["ingested_at"])

    if accessibility_text.strip():
        ax_hash_eligible += 1
        if content_hash:
            content_hash_present_count += 1

    if ingested_at is None or event_ts is None:
        capture_latency_anomaly_count += 1
    else:
        latency_ms = (ingested_at - event_ts).total_seconds() * 1000.0
        if latency_ms < 0:
            capture_latency_anomaly_count += 1
        else:
            capture_latency_values.append(latency_ms)

    if ingested_at is not None and isinstance(device_name, str) and device_name:
        previous = device_last_ingested.get(device_name)
        if previous is not None:
            inter_write_by_device[device_name].append(
                (ingested_at - previous).total_seconds()
            )
        device_last_ingested[device_name] = ingested_at

    if browser_url:
        browser_url_counts["browser_url_success"] += 1
    elif app_name in required_browser_apps:
        browser_url_counts["browser_url_failed_all_tiers"] += 1
    else:
        browser_url_counts["browser_url_skipped"] += 1

    if browser_url and (not app_name or not window_name):
        focused_context_mismatch_count += 1

content_hash_coverage = (
    (content_hash_present_count / ax_hash_eligible) if ax_hash_eligible > 0 else None
)

inter_write_gap_sec = {
    device_name: {
        "sample_count": len(samples),
        "max": max(samples) if samples else None,
        "p50": percentile(samples, 0.50),
        "p90": percentile(samples, 0.90),
        "p99": percentile(samples, 0.99),
    }
    for device_name, samples in sorted(inter_write_by_device.items())
}

capture_cycle_latency = {
    "sample_count": len(capture_latency_values),
    "anomaly_count": capture_latency_anomaly_count,
    "p50": percentile(capture_latency_values, 0.50),
    "p90": percentile(capture_latency_values, 0.90),
    "p95": percentile(capture_latency_values, 0.95),
    "p99": percentile(capture_latency_values, 0.99),
}

metrics_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "edge_pid": edge_pid,
            "host_pid": host_pid,
            "broken_window": broken_window,
            "git_rev": git_rev,
            "checks": {
                "content_hash_pytest": content_hash_status,
                "ax_timeout_pytest": ax_timeout_status,
                "focused_context_pytest": focused_context_status,
                "device_binding_pytest": device_binding_status,
                "browser_url_pytest": browser_url_status,
                "permission_recovery_pytest": permission_recovery_status,
                "health_snapshot": summary.get("health_status", "error"),
                "queue_snapshot": summary.get("queue_status", "error"),
                "db_metrics": "ok" if db_available else "missing",
            },
            "metrics": {
                "ax_hash_eligible": ax_hash_eligible,
                "content_hash_present_count": content_hash_present_count,
                "content_hash_coverage": content_hash_coverage,
                "inter_write_gap_sec": inter_write_gap_sec,
                "capture_cycle_latency": capture_cycle_latency,
                "browser_url_counts": dict(browser_url_counts),
                "focused_context_mismatch_count": focused_context_mismatch_count,
                "outcome_counts": dict(outcome_counts),
            },
            "context": {
                "base_url": base_url,
                "edge_db": str(edge_db),
                "health_snapshot_file": health_file.name,
                "proof_filter_file": proof_filter_path.name,
            },
        },
        indent=2,
    )
)

outcomes_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "counts": dict(outcome_counts),
        },
        indent=2,
    )
)

excluded_counts: Counter[str] = Counter(
    attempt["exclusion_reason"]
    for attempt in attempts
    if attempt["exclusion_reason"]
)

proof_filter_path.write_text(
    json.dumps(
        {
            "inputs": {
                "capture_attempts": "frames-derived",
                "ingest_decisions": "frames-derived",
                "health_snapshots": health_file.name,
            },
            "ruleset_version": "p1-s2b-v1",
            "attempts": attempts,
            "aggregates": {
                "total_attempts": len(attempts),
                "included_count": sum(1 for attempt in attempts if attempt["proof_status"] == "included"),
                "excluded_count": sum(1 for attempt in attempts if attempt["proof_status"] == "excluded"),
                "excluded_by_reason": dict(excluded_counts),
                "broken_window": broken_window,
                "restart_events": restart_events,
                "outcome_counts": dict(outcome_counts),
            },
        },
        indent=2,
    )
)

proof_filter = json.loads(proof_filter_path.read_text())
proof_filter["inputs"]["capture_attempts"] = (
    capture_attempts_path.name if capture_attempts else "frames-derived"
)
proof_filter["inputs"]["ingest_decisions"] = (
    ingest_decisions_path.name if ingest_decisions else "frames-derived"
)
proof_filter_path.write_text(json.dumps(proof_filter, indent=2))
PY

cat > "$UI_PROOF_FILE" <<EOF
# P1-S2b UI Evidence Index

- run_ts: $RUN_TS
- window_id: $WINDOW_ID
- edge_pid: $EDGE_PID
- host_pid: $HOST_PID
- base_url: $BASE_URL
- health_snapshots: $(basename "$HEALTH_FILE")
- outcomes: $(basename "$OUTCOMES_FILE")
- proof_filter: $(basename "$PROOF_FILTER_FILE")

## Required Proof Items

1. Timeline ('/timeline') new frame visibility proof
2. Browser URL extraction proof
3. Permission recovery / degraded state proof
4. Health anchor (#mr-health) proof

## Attachments

- Add screenshot/log references below:
  - [ ] Timeline evidence path:
  - [ ] Browser URL evidence path:
  - [ ] Permission recovery evidence path:
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
echo "  - $OUTCOMES_FILE"
echo "  - $PROOF_FILTER_FILE"
echo "  - $UI_PROOF_FILE"
echo "[INFO] Finished"

rm -f "$SAMPLER_SUMMARY_FILE" "$HEALTH_BODY_FILE" "$QUEUE_BODY_FILE"

exit "$EXIT_CODE"
