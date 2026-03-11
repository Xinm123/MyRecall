import os
from pathlib import Path
import json
import sqlite3
import subprocess

import pytest

from openrecall.server import __main__ as server_main


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "acceptance" / "p1_s2a_local.sh"


@pytest.mark.unit
def test_p1_s2a_local_script_exists_and_is_executable() -> None:
    assert SCRIPT_PATH.exists(), "scripts/acceptance/p1_s2a_local.sh must exist"
    assert SCRIPT_PATH.is_file()
    assert SCRIPT_PATH.stat().st_mode & 0o111, "script must be executable"


@pytest.mark.unit
def test_p1_s2a_local_script_help_returns_usage() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "p1_s2a_local.sh" in result.stdout
    assert "p1-s2a-trigger-channel-raw.jsonl" in result.stdout


def _seed_local_script_db(data_dir: Path) -> None:
    db_path = data_dir / "db" / "edge.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    server_main.ensure_v3_schema(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        for trigger_index, trigger in enumerate(
            ("idle", "app_switch", "manual", "click")
        ):
            for sample_index in range(20):
                capture_id = f"local-script-{trigger_index}-{sample_index}"
                timestamp = "2026-03-10T12:00:00Z"
                event_ts = f"2026-03-10T11:59:{sample_index:02d}Z"
                conn.execute(
                    """
                    INSERT INTO frames (
                        capture_id, timestamp, app_name, window_name, device_name,
                        snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        capture_id,
                        timestamp,
                        "Finder",
                        "Desktop",
                        f"monitor_{trigger_index % 2}",
                        f"/tmp/{capture_id}.jpg",
                        trigger,
                        event_ts,
                        "completed",
                        timestamp,
                        timestamp,
                    ),
                )
        conn.commit()


@pytest.mark.unit
def test_p1_s2a_local_script_writes_static_evidence_bundle(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    data_dir = tmp_path / "server-data"
    _seed_local_script_db(data_dir)

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

    metrics_path = evidence_dir / "p1-s2a-metrics.json"
    health_path = evidence_dir / "p1-s2a-health-snapshots.json"
    ui_proof_path = evidence_dir / "p1-s2a-ui-proof.md"
    raw_path = evidence_dir / "p1-s2a-trigger-channel-raw.jsonl"
    log_path = evidence_dir / "p1-s2a-local-gate.log"

    assert metrics_path.exists()
    assert health_path.exists()
    assert ui_proof_path.exists()
    assert raw_path.exists()
    assert log_path.exists()

    metrics = json.loads(metrics_path.read_text())
    assert metrics["window_id"]
    assert "edge_pid" in metrics
    assert "broken_window" in metrics
    assert metrics["metrics"]["trigger_coverage"] is not None
    assert metrics["metrics"]["capture_latency_sample_count"] is not None
    assert metrics["metrics"]["capture_latency_anomaly_count"] is not None
    assert metrics["metrics"]["collapse_trigger_count"] is not None
    assert metrics["metrics"]["queue_saturation_ratio"] is not None
    assert metrics["metrics"]["overflow_drop_count"] is not None
    assert "loss_rate" in metrics["metrics"]
    assert metrics["metrics"]["trigger_counts"] == {
        "idle": 20,
        "app_switch": 20,
        "manual": 20,
        "click": 20,
    }

    health = json.loads(health_path.read_text())
    assert health["snapshots"]
    assert {snapshot["endpoint"] for snapshot in health["snapshots"]} == {
        "/v1/health",
        "/v1/ingest/queue/status",
    }

    raw_lines = [line for line in raw_path.read_text().splitlines() if line.strip()]
    assert raw_lines
    raw_sample = json.loads(raw_lines[0])
    assert set(raw_sample) >= {
        "ts",
        "queue_depth",
        "queue_capacity",
        "collapse_trigger_count",
        "overflow_drop_count",
    }

    ui_proof = ui_proof_path.read_text()
    assert "Grid ('/') status visibility proof" in ui_proof
    assert "Timeline ('/timeline') new frame visibility proof" in ui_proof
    assert "Health anchor (#mr-health) proof" in ui_proof
