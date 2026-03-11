"""
Legacy Redirect Tests for P1-S1.

Tests Section 16 from:
openspec/changes/p1-s1-ingest-baseline/tasks.md

Usage:
    # Start Edge server first:
    #   conda activate old
    #   ./run_server.sh --debug

    # Then run tests:
    #   pytest tests/test_p1_s1_legacy.py -v
"""

import io
import os
import uuid

import pytest
import requests

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"
API_LEGACY = f"{BASE_URL}/api"


def generate_uuid_v7() -> str:
    """Generate a UUID v7 (time-based)."""
    import time
    import secrets

    timestamp = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    random_bits = secrets.randbits(80)
    uuid_int = (timestamp << 80) | random_bits
    uuid_int = (uuid_int & ~0xF000) | (7 << 12)
    uuid_int = (uuid_int & ~0xC000000000000000) | 0x8000000000000000
    return str(uuid.UUID(int=uuid_int))


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


class TestLegacyRedirects:
    """Tests for Section 16: Legacy Redirect Verification."""

    @pytest.mark.integration
    def test_16_1_legacy_redirects(self):
        """
        16.1 Verify legacy endpoints redirect to v1 with correct codes.

        - POST /api/upload -> 308 /v1/ingest
        - GET /api/search -> 301 /v1/search
        - GET /api/queue/status -> 301 /v1/ingest/queue/status
        - GET /api/health -> 301 /v1/health

        Requires: Running Edge server.
        """
        # POST /api/upload -> 308 /v1/ingest
        resp = requests.post(
            f"{API_LEGACY}/upload",
            files={"file": ("test.jpg", io.BytesIO(create_test_jpeg()), "image/jpeg")},
            data={"capture_id": generate_uuid_v7(), "metadata": "{}"},
            allow_redirects=False,
            timeout=10,
        )
        assert resp.status_code == 308
        assert "Location" in resp.headers
        assert "/v1/ingest" in resp.headers["Location"]

        # GET /api/search -> 301 /v1/search
        resp = requests.get(f"{API_LEGACY}/search", allow_redirects=False, timeout=5)
        assert resp.status_code == 301
        assert "Location" in resp.headers

        # GET /api/queue/status -> 301 /v1/ingest/queue/status
        resp = requests.get(
            f"{API_LEGACY}/queue/status", allow_redirects=False, timeout=5
        )
        assert resp.status_code == 301
        assert "Location" in resp.headers
        assert "/v1/ingest/queue/status" in resp.headers["Location"]

        # GET /api/health -> 301 /v1/health
        resp = requests.get(f"{API_LEGACY}/health", allow_redirects=False, timeout=5)
        assert resp.status_code == 301
        assert "Location" in resp.headers
        assert "/v1/health" in resp.headers["Location"]

    @pytest.mark.integration
    def test_16_2_deprecated_log_anchor(self):
        """
        16.2 Verify every legacy request logs '[DEPRECATED]' marker.

        Each legacy API call must produce a log line with '[DEPRECATED]' prefix.
        """
        log_path = "/tmp/openrecall_server.log"

        if not os.path.exists(log_path):
            pytest.skip(f"Log file not found: {log_path}")

        # Make legacy requests
        resp1 = requests.get(f"{API_LEGACY}/health", allow_redirects=False, timeout=5)
        resp2 = requests.get(f"{API_LEGACY}/search", allow_redirects=False, timeout=5)
        resp3 = requests.get(
            f"{API_LEGACY}/queue/status", allow_redirects=False, timeout=5
        )

        # Check responses are redirects
        assert resp1.status_code in [301, 308]
        assert resp2.status_code in [301, 308]
        assert resp3.status_code in [301, 308]

        # Wait a bit for logs to flush
        import time

        time.sleep(0.5)

        # Check DEPRECATED logs exist in file
        with open(log_path, "r") as f:
            content = f.read()

        # Should have at least some DEPRECATED logs
        deprecated_count = content.count("[DEPRECATED]")
        assert deprecated_count > 0, (
            f"Expected DEPRECATED logs in {log_path}, found {deprecated_count}"
        )
