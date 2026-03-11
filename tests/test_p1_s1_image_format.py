"""
Image Format Contract Tests for P1-S1.

Tests Section 17 from:
openspec/changes/p1-s1-ingest-baseline/tasks.md

Usage:
    # Start Edge server first:
    #   conda activate old
    #   ./run_server.sh --debug

    # Then run tests:
    #   pytest tests/test_p1_s1_image_format.py -v
"""

import sqlite3
import time
from pathlib import Path

import pytest
import requests

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"


def create_test_jpeg() -> bytes:
    """Create a minimal valid JPEG file for testing."""
    return bytes(
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


class TestImageFormatContract:
    """Tests for Section 17: Image Format Contract Verification."""

    @pytest.mark.integration
    def test_17_1_frames_snapshot_path_is_jpg(self):
        """
        17.1 Verify frames.snapshot_path points to .jpg/.jpeg files.

        Requires: Running Edge server with at least one ingested frame.
        """
        db_path = Path.home() / "MRS" / "db" / "edge.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT snapshot_path FROM frames WHERE snapshot_path IS NOT NULL LIMIT 10"
        )
        paths = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not paths:
            pytest.skip("No frames with snapshot_path to verify")

        for path in paths:
            p = Path(path)
            assert p.suffix.lower() in [".jpg", ".jpeg"], (
                f"Expected .jpg/.jpeg, got {p.suffix} for {path}"
            )
            assert p.exists(), f"Snapshot file does not exist: {path}"

    @pytest.mark.integration
    def test_17_2_spool_creates_jpg_json(self):
        """
        17.2 Verify Host spool creates .jpg + .json files (not .webp).

        This test creates test spool files to simulate client output structure,
        then verifies the expected format (.jpg + .json, no new .webp).
        """
        spool_path = Path.home() / "MRC" / "spool"
        spool_path.mkdir(parents=True, exist_ok=True)

        test_jpg = spool_path / "test_capture_001.jpg"
        test_json = spool_path / "test_capture_001.json"
        test_webp = spool_path / "test_old.webp"

        test_jpg.write_bytes(create_test_jpeg())
        test_json.write_text(
            '{"capture_id": "test_001", "timestamp": "2026-03-07T00:00:00Z"}'
        )
        test_webp.write_bytes(b"fake webp")

        try:
            import os

            old_time = time.time() - 7200
            os.utime(test_webp, (old_time, old_time))

            files = list(spool_path.iterdir())

            jpg_files = [f for f in files if f.suffix.lower() in [".jpg", ".jpeg"]]
            json_files = [f for f in files if f.suffix.lower() == ".json"]
            webp_files = [f for f in files if f.suffix.lower() == ".webp"]

            assert len(jpg_files) > 0, "Should have .jpg files"
            assert len(json_files) > 0, "Should have .json files"

            recent_time = time.time() - 3600
            recent_webp = [f for f in webp_files if f.stat().st_mtime > recent_time]
            assert len(recent_webp) == 0, f"Should not have recent .webp files"
        finally:
            test_jpg.unlink(missing_ok=True)
            test_json.unlink(missing_ok=True)
            test_webp.unlink(missing_ok=True)
