import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from openrecall.server import __main__ as server_main


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "acceptance" / "p1_s2b_local.sh"


@pytest.mark.unit
def test_p1_s2b_local_script_exists_and_is_executable() -> None:
    assert SCRIPT_PATH.exists(), "scripts/acceptance/p1_s2b_local.sh must exist"
    assert SCRIPT_PATH.is_file()
    assert SCRIPT_PATH.stat().st_mode & 0o111, "script must be executable"


@pytest.mark.unit
def test_p1_s2b_local_script_help_returns_usage() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "p1_s2b_local.sh" in result.stdout
    assert "p1-s2b-proof-filter.json" in result.stdout
    assert "p1-s2b-health-snapshots.json" in result.stdout
    assert "p1-s2b-outcomes.json" in result.stdout
    assert "p1-s2b-ui-proof.md" in result.stdout


def _seed_local_script_db(data_dir: Path) -> None:
    db_path = data_dir / "db" / "edge.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    server_main.ensure_v3_schema(db_path=db_path)

    rows = [
        {
            "capture_id": "s2b-local-1",
            "timestamp": "2026-03-12T12:00:00Z",
            "app_name": "Google Chrome",
            "window_name": "Example - Google Chrome",
            "browser_url": "https://example.com",
            "device_name": "monitor_0",
            "capture_trigger": "click",
            "event_ts": "2026-03-12T11:59:59Z",
            "ingested_at": "2026-03-12T12:00:03Z",
            "accessibility_text": "hello world",
            "content_hash": "sha256:" + "1" * 64,
        },
        {
            "capture_id": "s2b-local-2",
            "timestamp": "2026-03-12T12:00:10Z",
            "app_name": "Google Chrome",
            "window_name": "Example - Google Chrome",
            "browser_url": None,
            "device_name": "monitor_0",
            "capture_trigger": "app_switch",
            "event_ts": "2026-03-12T12:00:09Z",
            "ingested_at": "2026-03-12T12:00:12Z",
            "accessibility_text": "",
            "content_hash": None,
        },
        {
            "capture_id": "s2b-local-3",
            "timestamp": "2026-03-12T12:01:00Z",
            "app_name": "Safari",
            "window_name": "Docs",
            "browser_url": "https://docs.example.com",
            "device_name": "monitor_1",
            "capture_trigger": "manual",
            "event_ts": "2026-03-12T12:00:58Z",
            "ingested_at": "2026-03-12T12:01:05Z",
            "accessibility_text": "documentation",
            "content_hash": "sha256:" + "2" * 64,
        },
    ]

    with sqlite3.connect(str(db_path)) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO frames (
                    capture_id, timestamp, app_name, window_name, browser_url,
                    device_name, snapshot_path, capture_trigger, event_ts, status,
                    ingested_at, processed_at, accessibility_text, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["capture_id"],
                    row["timestamp"],
                    row["app_name"],
                    row["window_name"],
                    row["browser_url"],
                    row["device_name"],
                    f"/tmp/{row['capture_id']}.jpg",
                    row["capture_trigger"],
                    row["event_ts"],
                    "completed",
                    row["ingested_at"],
                    row["ingested_at"],
                    row["accessibility_text"],
                    row["content_hash"],
                ),
            )
        conn.commit()


@pytest.mark.unit
def test_p1_s2b_local_script_writes_static_evidence_bundle(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    data_dir = tmp_path / "server-data"
    _seed_local_script_db(data_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / ".p1-s2b-capture-attempts.jsonl").write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {
                    "capture_id": "s2b-local-1",
                    "outcome": "capture_completed",
                    "event_device_hint": "monitor_0",
                    "final_device_name": "monitor_0",
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "s2b-local-2",
                    "outcome": "permission_blocked",
                    "event_device_hint": "monitor_0",
                    "final_device_name": "monitor_0",
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "s2b-local-3",
                    "outcome": "dedup_skipped",
                    "event_device_hint": "monitor_1",
                    "final_device_name": "monitor_1",
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "attempt-4",
                    "outcome": "capture_completed",
                    "event_device_hint": "monitor_2",
                    "final_device_name": None,
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "attempt-5",
                    "outcome": "capture_completed",
                    "event_device_hint": "monitor_0",
                    "final_device_name": "monitor_0",
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": True,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "attempt-6",
                    "outcome": "capture_completed",
                    "event_device_hint": "monitor_0",
                    "final_device_name": "monitor_0",
                    "host_pid": 111,
                    "host_schema_version": "v2",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "attempt-7",
                    "outcome": "capture_completed",
                    "event_device_hint": "monitor_0",
                    "final_device_name": "monitor_0",
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
                {
                    "capture_id": "attempt-8",
                    "outcome": "capture_completed",
                    "event_device_hint": "monitor_0",
                    "final_device_name": "monitor_0",
                    "host_pid": 111,
                    "host_schema_version": "v3",
                    "alias_only_payload": False,
                    "missing_canonical_keys": False,
                    "final_device_name_mismatch": False,
                },
            ]
        ),
        encoding="utf-8",
    )
    (evidence_dir / ".p1-s2b-ingest-decisions.jsonl").write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {
                    "capture_id": "s2b-local-1",
                    "frame_id": 1,
                    "decision": "handoff_success",
                    "request_id": "req-1",
                    "edge_pid": 222,
                    "edge_schema_version": "v3",
                },
                {
                    "capture_id": "attempt-6",
                    "frame_id": 6,
                    "decision": "handoff_success",
                    "request_id": "req-6",
                    "edge_pid": 222,
                    "edge_schema_version": "v3",
                },
                {
                    "capture_id": "attempt-7",
                    "frame_id": None,
                    "decision": "schema_rejected",
                    "request_id": "req-7",
                    "edge_pid": 222,
                    "edge_schema_version": "v3",
                },
                {
                    "capture_id": "attempt-8",
                    "frame_id": None,
                    "decision": "queue_rejected",
                    "request_id": "req-8",
                    "edge_pid": 222,
                    "edge_schema_version": "v3",
                },
            ]
        ),
        encoding="utf-8",
    )

    env = {
        "OPENRECALL_SERVER_DATA_DIR": str(data_dir),
    }
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--skip-pytest",
            "--base-url",
            "http://127.0.0.1:9",
            "--evidence-dir",
            str(evidence_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ, **env},
    )

    assert result.returncode == 1

    metrics_path = evidence_dir / "p1-s2b-metrics.json"
    health_path = evidence_dir / "p1-s2b-health-snapshots.json"
    outcomes_path = evidence_dir / "p1-s2b-outcomes.json"
    proof_filter_path = evidence_dir / "p1-s2b-proof-filter.json"
    ui_proof_path = evidence_dir / "p1-s2b-ui-proof.md"
    log_path = evidence_dir / "p1-s2b-local-gate.log"

    assert metrics_path.exists()
    assert health_path.exists()
    assert outcomes_path.exists()
    assert proof_filter_path.exists()
    assert ui_proof_path.exists()
    assert log_path.exists()

    metrics = json.loads(metrics_path.read_text())
    assert metrics["window_id"]
    assert "edge_pid" in metrics
    assert "host_pid" in metrics
    assert "broken_window" in metrics
    assert metrics["metrics"]["ax_hash_eligible"] is not None
    assert metrics["metrics"]["content_hash_coverage"] is not None
    assert "inter_write_gap_sec" in metrics["metrics"]
    assert "capture_cycle_latency" in metrics["metrics"]
    assert "browser_url_counts" in metrics["metrics"]
    assert "focused_context_mismatch_count" in metrics["metrics"]

    health = json.loads(health_path.read_text())
    assert health["snapshots"]
    assert {snapshot["endpoint"] for snapshot in health["snapshots"]} == {
        "/v1/health",
        "/v1/ingest/queue/status",
    }

    outcomes = json.loads(outcomes_path.read_text())
    assert "counts" in outcomes
    assert set(outcomes["counts"]) >= {
        "capture_completed",
        "ax_empty",
        "ax_timeout_partial",
        "browser_url_rejected_stale",
        "permission_blocked",
        "dedup_skipped",
        "spool_failed",
        "schema_rejected",
    }
    assert outcomes["counts"]["permission_blocked"] == 1
    assert outcomes["counts"]["dedup_skipped"] == 1
    assert outcomes["counts"]["schema_rejected"] == 1

    proof_filter = json.loads(proof_filter_path.read_text())
    assert set(proof_filter) >= {"inputs", "ruleset_version", "attempts", "aggregates"}
    assert proof_filter["attempts"]
    assert (
        proof_filter["inputs"]["capture_attempts"] == ".p1-s2b-capture-attempts.jsonl"
    )
    assert (
        proof_filter["inputs"]["ingest_decisions"] == ".p1-s2b-ingest-decisions.jsonl"
    )
    attempt = proof_filter["attempts"][0]
    assert set(attempt) >= {
        "capture_id",
        "frame_id",
        "outcome",
        "proof_status",
        "exclusion_reason",
        "metric_eligibility",
        "final_device_name",
    }
    attempts_by_id = {item["capture_id"]: item for item in proof_filter["attempts"]}
    assert attempts_by_id["s2b-local-2"]["outcome"] == "permission_blocked"
    assert attempts_by_id["s2b-local-2"]["proof_status"] == "included"
    assert attempts_by_id["s2b-local-3"]["outcome"] == "dedup_skipped"
    assert attempts_by_id["s2b-local-3"]["proof_status"] == "included"
    assert (
        attempts_by_id["attempt-4"]["exclusion_reason"] == "final_device_name_missing"
    )
    assert attempts_by_id["attempt-5"]["exclusion_reason"] == "alias_only_payload"
    assert attempts_by_id["attempt-6"]["exclusion_reason"] == "mixed_version"
    assert attempts_by_id["attempt-7"]["exclusion_reason"] == "schema_rejected"
    assert attempts_by_id["attempt-8"]["exclusion_reason"] == "queue_rejected"
    assert proof_filter["aggregates"]["restart_events"] == []
    assert proof_filter["aggregates"]["broken_window"] is False

    ui_proof = ui_proof_path.read_text()
    assert "Timeline ('/timeline') new frame visibility proof" in ui_proof
    assert "Browser URL extraction proof" in ui_proof
    assert "Health anchor (#mr-health) proof" in ui_proof
