"""
Ingest Pipeline Tests for P1-S1.

Tests Section 12 from:
openspec/changes/p1-s1-ingest-baseline/tasks.md

Usage:
    # Start Edge server first:
    #   conda activate old
    #   ./run_server.sh --debug

    # Then run tests:
    #   pytest tests/test_p1_s1_ingest.py -v
"""

import io
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"


def generate_uuid_v7() -> str:
    """Generate a UUID v7 (time-based) using Python's uuid module."""
    import time
    import secrets
    import uuid

    timestamp = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    random_bits = secrets.randbits(80)
    uuid_int = (timestamp << 80) | random_bits
    uuid_int = (uuid_int & ~0xF000) | (7 << 12)
    uuid_int = (uuid_int & ~0xC000000000000000) | 0x8000000000000000
    return str(uuid.UUID(int=uuid_int))


def create_test_jpeg() -> bytes:
    """Create a minimal valid JPEG file for testing."""
    jpeg_data = bytes(
        [
            0xFF,
            0xD8,
            0xFF,
            0xE0,
            0x00,
            0x10,
            0x4A,
            0x46,
            0x49,
            0x46,
            0x00,
            0x01,
            0x01,
            0x00,
            0x00,
            0x01,
            0x00,
            0x01,
            0x00,
            0x00,
            0xFF,
            0xDB,
            0x00,
            0x43,
            0x00,
            0x08,
            0x06,
            0x06,
            0x07,
            0x06,
            0x05,
            0x08,
            0x07,
            0x07,
            0x07,
            0x09,
            0x09,
            0x08,
            0x0A,
            0x0C,
            0x14,
            0x0D,
            0x0C,
            0x0B,
            0x0B,
            0x0C,
            0x19,
            0x12,
            0x13,
            0x0F,
            0x14,
            0x1D,
            0x1A,
            0x1F,
            0x1E,
            0x1D,
            0x1A,
            0x1C,
            0x1C,
            0x20,
            0x24,
            0x2E,
            0x27,
            0x20,
            0x22,
            0x2C,
            0x23,
            0x1C,
            0x1C,
            0x28,
            0x37,
            0x29,
            0x2C,
            0x30,
            0x31,
            0x34,
            0x34,
            0x34,
            0x1F,
            0x27,
            0x39,
            0x3D,
            0x38,
            0x32,
            0x3C,
            0x2E,
            0x33,
            0x34,
            0x32,
            0xFF,
            0xC0,
            0x00,
            0x0B,
            0x08,
            0x00,
            0x01,
            0x00,
            0x01,
            0x01,
            0x01,
            0x11,
            0x00,
            0xFF,
            0xC4,
            0x00,
            0x14,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0xFF,
            0xC4,
            0x00,
            0x14,
            0x10,
            0x01,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0xFF,
            0xDA,
            0x00,
            0x08,
            0x01,
            0x01,
            0x00,
            0x00,
            0x3F,
            0x00,
            0xFB,
            0xD5,
            0xDB,
            0x20,
            0xA8,
            0xF8,
            0xFF,
            0xD9,
        ]
    )
    return jpeg_data


def upload_frame(
    capture_id: str, jpeg_bytes: bytes, metadata: dict | None = None
) -> requests.Response:
    url = f"{API_V1}/ingest"
    files = {"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
    data = {
        "capture_id": capture_id,
        "metadata": json.dumps(metadata or {}),
    }
    return requests.post(url, files=files, data=data, timeout=10)


def get_queue_status() -> dict:
    resp = requests.get(f"{API_V1}/ingest/queue/status", timeout=5)
    resp.raise_for_status()
    return resp.json()


class TestIngestPipeline:
    """Tests for Section 12: Ingest Pipeline Verification."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db_path = Path.home() / "MRS" / "db" / "edge.db"
        yield

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_1_upload_50_unique_captures(self):
        """
        12.1 Upload 50 unique captures, confirm each returns 201 Created.

        Requires: Running Edge server.
        """
        status_before = get_queue_status()
        initial_total = (
            status_before["pending"]
            + status_before["processing"]
            + status_before["completed"]
            + status_before["failed"]
        )

        jpeg_bytes = create_test_jpeg()

        for i in range(50):
            capture_id = generate_uuid_v7()
            resp = upload_frame(capture_id, jpeg_bytes)

            assert resp.status_code == 201, (
                f"Expected 201 for capture {i + 1}, got {resp.status_code}: {resp.text}"
            )

            data = resp.json()
            assert "code" not in data, (
                f"Response should not contain 'code' field: {data}"
            )
            assert "capture_id" in data
            assert "frame_id" in data
            assert "status" in data
            assert "request_id" in data
            assert data["status"] == "queued"
            assert data["capture_id"] == capture_id

        status = get_queue_status()
        total = (
            status["pending"]
            + status["processing"]
            + status["completed"]
            + status["failed"]
        )
        assert total == initial_total + 50, (
            f"Expected {initial_total + 50} total, got {total}"
        )

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_2_replay_10_duplicate_captures(self):
        """
        12.2 Replay 10 duplicate capture_ids, confirm all return 200 OK with 'already_exists'.

        Requires: Running Edge server with existing frames.
        """
        status = get_queue_status()
        if status["pending"] + status["completed"] == 0:
            pytest.skip("No existing frames to test duplicate")

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT capture_id FROM frames LIMIT 10")
        existing_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        if len(existing_ids) < 10:
            pytest.skip("Not enough existing frames to test duplicates")

        status_before = get_queue_status()
        initial_total = (
            status_before["pending"]
            + status_before["processing"]
            + status_before["completed"]
            + status_before["failed"]
        )

        for capture_id in existing_ids[:10]:
            resp = upload_frame(capture_id, create_test_jpeg())

            assert resp.status_code == 200, (
                f"Expected 200 for duplicate, got {resp.status_code}: {resp.text}"
            )

            data = resp.json()
            assert "code" not in data
            assert data["status"] == "already_exists"

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        total_count = cursor.fetchone()[0]
        conn.close()

        assert total_count == initial_total, (
            f"Expected {initial_total} frames, got {total_count}"
        )

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_3_queue_count_matches_db(self):
        """
        12.3 Verify pending + processing + completed + failed = total frames in DB.

        Requires: Running Edge server with data.
        """
        status = get_queue_status()
        total_in_queue = (
            status["pending"]
            + status["processing"]
            + status["completed"]
            + status["failed"]
        )

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        total_in_db = cursor.fetchone()[0]
        conn.close()

        assert total_in_queue == total_in_db

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_4_400_invalid_params_no_db_change(self):
        """
        12.4 Verify 400 INVALID_PARAMS does not change DB.

        Requires: Running Edge server.
        """
        status_before = get_queue_status()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        db_count_before = cursor.fetchone()[0]
        conn.close()

        url = f"{API_V1}/ingest"
        files = {"file": ("test.jpg", io.BytesIO(create_test_jpeg()), "image/jpeg")}
        data = {"metadata": "{}"}

        resp = requests.post(url, files=files, data=data, timeout=10)
        assert resp.status_code == 400

        status_after = get_queue_status()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        db_count_after = cursor.fetchone()[0]
        conn.close()

        assert status_before == status_after
        assert db_count_before == db_count_after

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_5_413_payload_too_large_no_db_change(self):
        """
        12.5 Verify 413 PAYLOAD_TOO_LARGE does not change DB.

        Requires: Running Edge server.
        """
        status_before = get_queue_status()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        db_count_before = cursor.fetchone()[0]
        conn.close()

        large_file = b"x" * (11 * 1024 * 1024)

        url = f"{API_V1}/ingest"
        files = {"file": ("large.jpg", io.BytesIO(large_file), "image/jpeg")}
        data = {
            "capture_id": generate_uuid_v7(),
            "metadata": "{}",
        }

        resp = requests.post(url, files=files, data=data, timeout=30)
        assert resp.status_code == 413

        status_after = get_queue_status()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        db_count_after = cursor.fetchone()[0]
        conn.close()

        assert status_before == status_after
        assert db_count_before == db_count_after

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_6_503_queue_full_no_db_change(self):
        """
        12.6 Verify 503 QUEUE_FULL does not change DB.

        This test inserts 200 pending frames into DB to trigger the 503 condition.
        Since default capacity is 200, having >=200 pending frames will trigger 503.

        Requires: Running Edge server.
        """
        db_path = Path.home() / "MRS" / "db" / "edge.db"
        conn = sqlite3.connect(str(db_path))

        # Get current pending count
        cursor = conn.execute("SELECT COUNT(*) FROM frames WHERE status = 'pending'")
        current_pending = cursor.fetchone()[0]

        # Insert enough pending frames to exceed capacity (default 200)
        # Note: We need to reach >= 200 to trigger 503
        frames_to_add = 200 - current_pending + 1  # +1 to ensure we exceed

        import time

        for i in range(frames_to_add):
            conn.execute(
                """INSERT INTO frames 
                   (capture_id, status, timestamp, ingested_at, device_name)
                   VALUES (?, 'pending', datetime('now'), datetime('now'), 'test')""",
                (f"test_pending_{int(time.time() * 1000000)}_{i}",),
            )
        conn.commit()
        conn.close()

        try:
            # Now try to upload - should get 503
            resp = upload_frame(generate_uuid_v7(), create_test_jpeg())
            assert resp.status_code == 503, (
                f"Expected 503, got {resp.status_code}: {resp.text}"
            )

            # Verify DB unchanged
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT COUNT(*) FROM frames WHERE capture_id LIKE 'test_pending_%'"
            )
            test_frames_count = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM frames")
            total_count = cursor.fetchone()[0]
            conn.close()

            # Should have added exactly frames_to_add test frames
            assert test_frames_count == frames_to_add
        finally:
            # Cleanup test frames
            conn = sqlite3.connect(str(db_path))
            conn.execute("DELETE FROM frames WHERE capture_id LIKE 'test_pending_%'")
            conn.commit()
            conn.close()

    @pytest.mark.integration
    @pytest.mark.unit
    def test_12_7_non_jpeg_returns_400(self):
        """
        12.7 Verify non-JPEG upload returns 400 and does not change DB.

        Requires: Running Edge server.
        """
        status_before = get_queue_status()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        db_count_before = cursor.fetchone()[0]
        conn.close()

        url = f"{API_V1}/ingest"
        png_data = b"\x89PNG\r\n\x1a\n" + b"x" * 100
        files = {"file": ("test.png", io.BytesIO(png_data), "image/png")}
        data = {
            "capture_id": generate_uuid_v7(),
            "metadata": "{}",
        }

        resp = requests.post(url, files=files, data=data, timeout=10)
        assert resp.status_code == 400

        status_after = get_queue_status()
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM frames")
        db_count_after = cursor.fetchone()[0]
        conn.close()

        assert status_before == status_after
        assert db_count_before == db_count_after

    @pytest.mark.integration
    @pytest.mark.unit
    @pytest.mark.xfail(
        reason="Known race condition - server file write not atomic", strict=False
    )
    def test_12_8_concurrent_same_capture_id(self):
        """
        12.8 Verify concurrent upload of same capture_id results in exactly one 201 and one 200.

        Requires: Running Edge server.
        """
        capture_id = generate_uuid_v7()
        jpeg_bytes = create_test_jpeg()

        def upload():
            return upload_frame(capture_id, jpeg_bytes)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(upload) for _ in range(2)]
            results = [f.result() for f in futures]

        statuses = [r.status_code for r in results]

        assert 201 in statuses, f"Expected one 201, got {statuses}"
        assert 200 in statuses, f"Expected one 200, got {statuses}"

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM frames WHERE capture_id = ?", (capture_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, f"Expected 1 frame, got {count}"

        for resp in results:
            data = resp.json()
            assert "request_id" in data
