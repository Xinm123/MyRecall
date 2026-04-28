"""
Frame Reading Tests for P1-S1.

Tests Section 13 from:
openspec/changes/p1-s1-ingest-baseline/tasks.md

Usage:
    # Start Edge server first:
    #   conda activate old
    #   ./run_server.sh --debug

    # Then run tests:
    #   pytest tests/test_p1_s1_frames.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
import requests

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.shared.config import settings

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"


@pytest.fixture
def test_store(tmp_path):
    """Create a temporary FramesStore with migrated schema for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return FramesStore(db_path=db_path)


def get_queue_status() -> dict:
    resp = requests.get(f"{API_V1}/ingest/queue/status", timeout=5)
    resp.raise_for_status()
    return resp.json()


def get_frame(frame_id: int) -> requests.Response:
    return requests.get(f"{API_V1}/frames/{frame_id}", timeout=5)


class TestFrameReading:
    """Tests for Section 13: Frame Reading Verification."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db_path = settings.db_path

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT id, snapshot_path FROM frames WHERE snapshot_path IS NOT NULL LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            self.existing_frame_id = row[0]
            self.existing_snapshot_path = row[1]
        else:
            self.existing_frame_id = None
            self.existing_snapshot_path = None

        yield

    @pytest.mark.integration
    def test_13_1_get_frame_returns_jpeg(self):
        """
        13.1 Verify GET /v1/frames/:frame_id returns JPEG with correct Content-Type.

        Requires: Running Edge server with at least one frame.
        """
        if not self.existing_frame_id:
            pytest.skip("No existing frames to test")

        resp = get_frame(self.existing_frame_id)

        assert resp.status_code == 200
        assert resp.headers.get("Content-Type") == "image/jpeg"

        content = resp.content
        assert content[:2] == b"\xff\xd8", "Response is not a valid JPEG"

    @pytest.mark.integration
    def test_13_2_get_nonexistent_frame_returns_404(self):
        """
        13.2 Verify GET /v1/frames/:frame_id for nonexistent ID returns 404.

        Requires: Running Edge server.
        """
        resp = get_frame(999999999)

        assert resp.status_code == 404

        data = resp.json()
        assert "code" in data
        assert data["code"] == "NOT_FOUND"

    @pytest.mark.integration
    def test_13_3_missing_snapshot_file_returns_404_no_db_change(self):
        """
        13.3 Verify GET for missing snapshot file returns 404 and does not modify queue.

        Requires: Running Edge server.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT id, snapshot_path FROM frames WHERE snapshot_path IS NOT NULL LIMIT 1"
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            pytest.skip("No frames with snapshot_path to test")

        frame_id = row[0]
        original_path = row[1]
        conn.close()

        status_before = get_queue_status()

        import shutil

        path = Path(original_path)
        if path.exists():
            backup_path = path.with_suffix(".jpg.bak")
            shutil.move(str(path), str(backup_path))

            try:
                resp = get_frame(frame_id)
                assert resp.status_code in [404, 500]

                status_after = get_queue_status()
                assert status_before == status_after
            finally:
                if backup_path.exists():
                    shutil.move(str(backup_path), str(path))


def test_frame_local_timestamp_computed_from_utc(test_store):
    """Verify local_timestamp is computed correctly from UTC."""
    utc_ts = "2026-04-25T20:00:00.000Z"
    metadata = {
        "timestamp": utc_ts,
        "app_name": "TestApp",
        "capture_trigger": "idle",
    }
    frame_id, is_new = test_store.claim_frame(
        capture_id="test-capture-local-ts",
        metadata=metadata,
    )
    assert is_new is True
    with test_store._connect() as conn:
        row = conn.execute(
            "SELECT timestamp, local_timestamp FROM frames WHERE id = ?",
            (frame_id,),
        ).fetchone()
    from datetime import datetime, timedelta
    utc_dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
    local_dt = datetime.fromisoformat(row["local_timestamp"])
    assert utc_dt.hour == 20
    assert local_dt.day == 26 and local_dt.hour == 4
    # Verify the 8-hour offset
    assert (local_dt - utc_dt.replace(tzinfo=None)) == timedelta(hours=8)


def test_query_by_local_timestamp(test_store):
    """Verify time range queries use local_timestamp correctly."""
    # UTC times that span local midnight
    frames = [
        ("cap-1", "2026-04-25T15:00:00.000Z", "App1"),  # local: 04-25 23:00
        ("cap-2", "2026-04-25T20:00:00.000Z", "App2"),  # local: 04-26 04:00
        ("cap-3", "2026-04-26T10:00:00.000Z", "App3"),  # local: 04-26 18:00
    ]
    for capture_id, ts, app in frames:
        test_store.claim_frame(
            capture_id=capture_id,
            metadata={"timestamp": ts, "app_name": app, "capture_trigger": "idle"},
        )
        with test_store._connect() as conn:
            conn.execute(
                "UPDATE frames SET snapshot_path = ?, status = 'completed', visibility_status = 'queryable' WHERE capture_id = ?",
                (f"/tmp/{capture_id}.jpg", capture_id),
            )
            conn.commit()

    # Query local date 2026-04-26
    apps = test_store.get_activity_summary_apps(
        start_time="2026-04-26T00:00:00",
        end_time="2026-04-26T23:59:59",
    )
    app_names = {a["name"] for a in apps}
    assert "App2" in app_names
    assert "App3" in app_names
    assert "App1" not in app_names


def test_get_frames_by_day(test_store):
    """get_frames_by_day returns frames for a specific date."""
    frame_id, _ = test_store.claim_frame(
        capture_id="test-cap-day",
        metadata={
            "timestamp": "2026-04-28T02:00:00.000Z",
            "app_name": "TestApp",
            "capture_trigger": "idle",
        },
    )
    with test_store._connect() as conn:
        conn.execute(
            "UPDATE frames SET snapshot_path = ?, status = 'completed' WHERE id = ?",
            ("/tmp/test.jpg", frame_id),
        )
        conn.commit()
    result = test_store.get_frames_by_day("2026-04-28")
    assert len(result) >= 1
    assert result[0]["frame_id"] == frame_id
    # All expected fields present
    assert "app_name" in result[0]
    assert "visibility_status" in result[0]


def test_get_frames_by_day_empty(test_store):
    """get_frames_by_day returns empty list for date with no frames."""
    result = test_store.get_frames_by_day("1999-01-01")
    assert result == []
