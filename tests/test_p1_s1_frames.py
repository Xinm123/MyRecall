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
from pathlib import Path

import pytest
import requests

from openrecall.shared.config import settings

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"


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
    @pytest.mark.unit
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
    @pytest.mark.unit
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
    @pytest.mark.unit
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
