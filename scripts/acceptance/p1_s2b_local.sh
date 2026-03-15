#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: p1_s2b_local.sh [options]

Run local P1-S2b gate checks and produce a standard evidence bundle.

Options:
  --base-url URL            Edge base URL (default: http://localhost:${OPENRECALL_PORT:-8083})
  --evidence-dir DIR        Evidence output directory
                            (default: docs/v3/acceptance/phase1/evidence)
  --window-id ID            Custom window_id for this run
  --edge-pid PID            Edge process id for metadata (optional)
  --edge-db PATH            Override edge.db path
  --sample-seconds N        1Hz sampling window for health snapshots (default: 5)
  --topology-method METHOD  Topology verification method: injected|manual (default: injected)
  --topology-notes FILE     Optional operator notes file for manual topology steps
  --exclude-broken-window   Mark proof window as excluded
  --exclude-alias-only      Mark alias-only payload samples excluded
  --exclude-mixed-version   Mark mixed-version samples excluded
  --skip-pytest             Skip pytest checks (still produce evidence files)
  -h, --help                Show this help and exit

Outputs:
  - p1-s2b-local-gate.log
  - p1-s2b-metrics.json
  - p1-s2b-health-snapshots.json
  - p1-s2b-spool-check.json
  - p1-s2b-context.json
  - p1-s2b-topology-evidence.json
  - p1-s2b-proof-samples.json
  - p1-s2b-ui-proof.md
EOF
}

BASE_URL="http://localhost:${OPENRECALL_PORT:-8083}"
EVIDENCE_DIR="docs/v3/acceptance/phase1/evidence"
WINDOW_ID=""
EDGE_PID=""
EDGE_DB=""
SAMPLE_SECONDS=5
TOPOLOGY_METHOD="injected"
TOPOLOGY_NOTES=""
EXCLUDE_BROKEN_WINDOW=0
EXCLUDE_ALIAS_ONLY=0
EXCLUDE_MIXED_VERSION=0
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
    --topology-method)
      TOPOLOGY_METHOD="$2"
      shift 2
      ;;
    --topology-notes)
      TOPOLOGY_NOTES="$2"
      shift 2
      ;;
    --exclude-broken-window)
      EXCLUDE_BROKEN_WINDOW=1
      shift
      ;;
    --exclude-alias-only)
      EXCLUDE_ALIAS_ONLY=1
      shift
      ;;
    --exclude-mixed-version)
      EXCLUDE_MIXED_VERSION=1
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

RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_TAG="$(date -u +%Y%m%dT%H%M%SZ)"
WINDOW_ID="${WINDOW_ID:-p1-s2b-${RUN_TAG}}"
EDGE_PID="${EDGE_PID:-unknown}"
EDGE_DB="${EDGE_DB:-${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/db/edge.db}"
GIT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
HOSTNAME_VAL="$(hostname 2>/dev/null || echo unknown-host)"

LOG_FILE="$EVIDENCE_DIR/p1-s2b-local-gate.log"
METRICS_FILE="$EVIDENCE_DIR/p1-s2b-metrics.json"
HEALTH_FILE="$EVIDENCE_DIR/p1-s2b-health-snapshots.json"
CONTEXT_FILE="$EVIDENCE_DIR/p1-s2b-context.json"
TOPOLOGY_FILE="$EVIDENCE_DIR/p1-s2b-topology-evidence.json"
PROOF_FILE="$EVIDENCE_DIR/p1-s2b-proof-samples.json"
SPOOL_FILE="$EVIDENCE_DIR/p1-s2b-spool-check.json"
UI_PROOF_FILE="$EVIDENCE_DIR/p1-s2b-ui-proof.md"
SAMPLER_SUMMARY_FILE="$EVIDENCE_DIR/.p1-s2b-sampler-summary.json"

exec > >(tee "$LOG_FILE") 2>&1

echo "[INFO] P1-S2b local gate started"
echo "[INFO] run_ts=$RUN_TS"
echo "[INFO] window_id=$WINDOW_ID"
echo "[INFO] edge_pid=$EDGE_PID"
echo "[INFO] base_url=$BASE_URL"
echo "[INFO] evidence_dir=$EVIDENCE_DIR"
echo "[INFO] edge_db=$EDGE_DB"
echo "[INFO] sample_seconds=$SAMPLE_SECONDS"
echo "[INFO] topology_method=$TOPOLOGY_METHOD"
echo "[INFO] git_rev=$GIT_REV"
echo "[INFO] hostname=$HOSTNAME_VAL"

FAIL_COUNT=0
ROUTING_SUITE_STATUS="not_run"
BINDING_SUITE_STATUS="not_run"
REGRESSION_SUITE_STATUS="not_run"

SC_R1_STATUS="not_run"
SC_R2_STATUS="not_run"
SC_F1_STATUS="not_run"
SC_I1_STATUS="not_run"
SC_I2_STATUS="not_run"
SC_O1_STATUS="not_run"
SC_T1_STATUS="not_run"
SC_T2_STATUS="not_run"
SC_T3_STATUS="not_run"
SC_T4_STATUS="not_run"

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

run_pytest_node() {
  local nodeid="$1"
  local status_var="$2"
  if pytest "$nodeid" -q; then
    printf -v "$status_var" '%s' "pass"
  else
    printf -v "$status_var" '%s' "fail"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

if [[ "$SKIP_PYTEST" -eq 1 ]]; then
  ROUTING_SUITE_STATUS="skipped"
  BINDING_SUITE_STATUS="skipped"
  REGRESSION_SUITE_STATUS="skipped"
  SC_R1_STATUS="skipped"
  SC_R2_STATUS="skipped"
  SC_F1_STATUS="skipped"
  SC_I1_STATUS="skipped"
  SC_I2_STATUS="skipped"
  SC_O1_STATUS="skipped"
  SC_T1_STATUS="skipped"
  SC_T2_STATUS="skipped"
  SC_T3_STATUS="skipped"
  SC_T4_STATUS="skipped"
else
  run_pytest_check "tests/test_p1_s2b_routing.py" ROUTING_SUITE_STATUS
  run_pytest_check "tests/test_p1_s2b_device_binding.py" BINDING_SUITE_STATUS
  if pytest tests/test_p1_s2a_server_contracts.py tests/test_p1_s2a_recorder.py tests/test_p1_s2a_device_binding.py -q; then
    REGRESSION_SUITE_STATUS="pass"
  else
    REGRESSION_SUITE_STATUS="fail"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  run_pytest_node "tests/test_p1_s2b_routing.py::test_click_routes_to_primary_monitor_when_target_is_primary" SC_R1_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_click_routes_to_specific_monitor" SC_R2_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_filtered_routing_produces_outcome_without_spool_enqueue" SC_F1_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_per_monitor_idle_partitions_reset_independently" SC_I1_STATUS
  run_pytest_node "tests/test_p1_s2b_device_binding.py::test_non_focused_capture_writes_null_context" SC_I2_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_same_monitor_debounce_and_cross_monitor_independence" SC_O1_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_topology_add_monitor_scenario" SC_T1_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_topology_remove_monitor_scenario" SC_T2_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_topology_primary_switch_updates_manual_target" SC_T3_STATUS
  run_pytest_node "tests/test_p1_s2b_routing.py::test_topology_rebuild_add_remove_and_recovery" SC_T4_STATUS
fi

python3 - "$BASE_URL" "$SAMPLE_SECONDS" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$HEALTH_FILE" "$SAMPLER_SUMMARY_FILE" <<'PY'
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
summary_path = Path(sys.argv[7])

snapshots = []
health_status = "error"
health_code = 0

for index in range(sample_seconds):
    sample_ts = utc_now_iso()
    status, code, payload = fetch_json(base_url, "/v1/health")
    health_status = status
    health_code = code
    capture_runtime = payload.get("capture_runtime") if isinstance(payload, dict) else {}
    if not isinstance(capture_runtime, dict):
        capture_runtime = {}
    snapshots.append(
        {
            "ts": sample_ts,
            "status": status,
            "http_code": code,
            "capture_runtime": capture_runtime,
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
summary_path.write_text(json.dumps({"health_status": health_status, "health_code": health_code}, indent=2))
PY

HEALTH_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["health_status"])' "$SAMPLER_SUMMARY_FILE")"

TOPOLOGY_ALL_PASS=0
if [[ "$HEALTH_STATUS" == "ok" && "$SC_T1_STATUS" == "pass" && "$SC_T2_STATUS" == "pass" && "$SC_T3_STATUS" == "pass" && "$SC_T4_STATUS" == "pass" ]]; then
  TOPOLOGY_ALL_PASS=1
fi

TOPOLOGY_ARGS=("--method" "$TOPOLOGY_METHOD" "--output" "$TOPOLOGY_FILE")
if [[ -n "$TOPOLOGY_NOTES" ]]; then
  TOPOLOGY_ARGS+=("--notes-file" "$TOPOLOGY_NOTES")
fi
if [[ "$TOPOLOGY_ALL_PASS" -eq 1 ]]; then
  TOPOLOGY_ARGS+=("--all-pass")
fi
python3 "scripts/acceptance/p1_s2b_topology_helper.py" "${TOPOLOGY_ARGS[@]}"

python3 - "$METRICS_FILE" "$PROOF_FILE" "$CONTEXT_FILE" "$SPOOL_FILE" "$RUN_TS" "$WINDOW_ID" "$EDGE_PID" "$GIT_REV" "$BASE_URL" "$EDGE_DB" "$HEALTH_STATUS" "$ROUTING_SUITE_STATUS" "$BINDING_SUITE_STATUS" "$REGRESSION_SUITE_STATUS" "$SC_R1_STATUS" "$SC_R2_STATUS" "$SC_F1_STATUS" "$SC_I1_STATUS" "$SC_I2_STATUS" "$SC_O1_STATUS" "$SC_T1_STATUS" "$SC_T2_STATUS" "$SC_T3_STATUS" "$SC_T4_STATUS" "$EXCLUDE_BROKEN_WINDOW" "$EXCLUDE_ALIAS_ONLY" "$EXCLUDE_MIXED_VERSION" <<'PY'
from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * pct
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


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


metrics_path = Path(sys.argv[1])
proof_path = Path(sys.argv[2])
context_path = Path(sys.argv[3])
spool_path = Path(sys.argv[4])
run_ts = sys.argv[5]
window_id = sys.argv[6]
edge_pid = sys.argv[7]
git_rev = sys.argv[8]
base_url = sys.argv[9]
edge_db = Path(sys.argv[10])
health_status = sys.argv[11]
routing_suite = sys.argv[12]
binding_suite = sys.argv[13]
regression_suite = sys.argv[14]
sc_r1 = sys.argv[15]
sc_r2 = sys.argv[16]
sc_f1 = sys.argv[17]
sc_i1 = sys.argv[18]
sc_i2 = sys.argv[19]
sc_o1 = sys.argv[20]
sc_t1 = sys.argv[21]
sc_t2 = sys.argv[22]
sc_t3 = sys.argv[23]
sc_t4 = sys.argv[24]
exclude_broken_window = bool(int(sys.argv[25]))
exclude_alias_only = bool(int(sys.argv[26]))
exclude_mixed_version = bool(int(sys.argv[27]))

scenario_status = {
    "SC-R1": sc_r1,
    "SC-R2": sc_r2,
    "SC-F1": sc_f1,
    "SC-I1": sc_i1,
    "SC-I2": sc_i2,
    "SC-O1": sc_o1,
    "SC-T1": sc_t1,
    "SC-T2": sc_t2,
    "SC-T3": sc_t3,
    "SC-T4": sc_t4,
}

def ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    return (sum(1 for value in values if value == "pass") / len(values)) * 100.0


routing_correctness = ratio([sc_r1, sc_r2, sc_f1, sc_i1, sc_i2, sc_o1])
binding_correctness = 100.0 if binding_suite == "pass" else 0.0
topology_correctness = ratio([sc_t1, sc_t2, sc_t3, sc_t4])
duplicate_rate = 0.0 if sc_o1 == "pass" else 100.0

latency_by_device: dict[str, list[float]] = {}
alias_only_count = 0
mixed_version_count = 0
source_window_start = parse_utc(run_ts)
source_window_end = datetime.now(timezone.utc)
if edge_db.exists():
    with sqlite3.connect(str(edge_db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT device_name, timestamp, ingested_at, capture_trigger
            FROM frames
            ORDER BY id ASC
            """
        ).fetchall()
        for row in rows:
            device_name = str(row["device_name"] or "")
            if not device_name or not row["capture_trigger"]:
                alias_only_count += 1
                continue
            timestamp_dt = parse_utc(row["timestamp"])
            ingested_dt = parse_utc(row["ingested_at"])
            if timestamp_dt is None or ingested_dt is None:
                continue
            if source_window_start is not None:
                if not (source_window_start <= ingested_dt <= source_window_end):
                    continue
            if timestamp_dt.year < 2026:
                mixed_version_count += 1
                continue
            latency_ms = (ingested_dt - timestamp_dt).total_seconds() * 1000.0
            if latency_ms < 0:
                continue
            latency_by_device.setdefault(device_name, []).append(latency_ms)

latency_summary = {}
for device_name, values in latency_by_device.items():
    latency_summary[device_name] = {
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "sample_count": len(values),
    }

broken_window = exclude_broken_window or health_status != "ok"
proof_rules = {
    "broken_window": broken_window,
    "alias_only_excluded": exclude_alias_only or alias_only_count > 0,
    "mixed_version_excluded": exclude_mixed_version or mixed_version_count > 0,
    "alias_only_count": alias_only_count,
    "mixed_version_count": mixed_version_count,
}

spool_dir = Path.home() / "MRC" / "spool"
spool_items = []
if spool_dir.exists():
    for metadata_file in sorted(spool_dir.glob("*.json")):
        try:
            payload = json.loads(metadata_file.read_text())
        except Exception:
            continue
        capture_id = str(payload.get("capture_id") or metadata_file.stem)
        image_file = spool_dir / f"{capture_id}.jpg"
        spool_items.append(
            {
                "capture_id": capture_id,
                "has_image": image_file.exists(),
                "device_name": payload.get("device_name"),
                "capture_trigger": payload.get("capture_trigger"),
            }
        )
spool_path.write_text(
    json.dumps(
        {
            "spool_dir": str(spool_dir),
            "item_count": len(spool_items),
            "items": spool_items,
        },
        indent=2,
    )
)

if broken_window:
    routing_metric: float | None = None
    binding_metric: float | None = None
    duplicate_metric: float | None = None
    topology_metric: float | None = None
else:
    routing_metric = routing_correctness
    binding_metric = binding_correctness
    duplicate_metric = duplicate_rate
    topology_metric = topology_correctness

metrics_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "edge_pid": edge_pid,
            "git_rev": git_rev,
            "checks": {
                "routing_suite": routing_suite,
                "binding_suite": binding_suite,
                "regression_suite": regression_suite,
                "health_status": health_status,
            },
            "scenario_status": scenario_status,
            "metrics": {
                "trigger_target_routing_correctness": routing_metric,
                "device_binding_correctness": binding_metric,
                "single_monitor_duplicate_capture_rate": duplicate_metric,
                "topology_rebuild_correctness": topology_metric,
                "capture_to_ingest_latency_ms": latency_summary,
            },
            "proof_sample_rules": proof_rules,
            "spool_check_file": spool_path.name,
        },
        indent=2,
    )
)

proof_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "scenario_status": scenario_status,
            "proof_sample_rules": proof_rules,
            "spool_check_file": spool_path.name,
        },
        indent=2,
    )
)

context_path.write_text(
    json.dumps(
        {
            "run_ts": run_ts,
            "window_id": window_id,
            "edge_pid": edge_pid,
            "base_url": base_url,
            "edge_db": str(edge_db),
            "git_rev": git_rev,
            "source_window": {
                "start": run_ts,
                "end": source_window_end.isoformat().replace("+00:00", "Z"),
            },
        },
        indent=2,
    )
)
PY

cat > "$UI_PROOF_FILE" <<EOF
# P1-S2b UI Evidence Index

- run_ts: $RUN_TS
- window_id: $WINDOW_ID
- edge_pid: $EDGE_PID
- topology_method: $TOPOLOGY_METHOD

## Routing Scenarios
- [ ] SC-R1 same-monitor click proof
- [ ] SC-R2 cross-monitor click proof
- [ ] SC-F1 routing_filtered proof
- [ ] SC-I1 per-monitor idle proof
- [ ] SC-I2 non-focused null-context proof
- [ ] SC-O1 one-action debounce proof

## Topology Scenarios
- [ ] SC-T1 monitor add proof
- [ ] SC-T2 monitor remove proof
- [ ] SC-T3 primary switch proof
- [ ] SC-T4 recovery proof

## Exclusion Records
- [ ] broken_window evidence
- [ ] alias-only payload evidence
- [ ] mixed-version evidence
EOF

if [[ "$HEALTH_STATUS" != "ok" ]]; then
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

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
echo "  - $SPOOL_FILE"
echo "  - $CONTEXT_FILE"
echo "  - $TOPOLOGY_FILE"
echo "  - $PROOF_FILE"
echo "  - $UI_PROOF_FILE"

rm -f "$SAMPLER_SUMMARY_FILE"

exit "$EXIT_CODE"
