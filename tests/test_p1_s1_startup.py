"""
Startup and Basic Verification Tests for P1-S1.

Tests Section 11 from:
openspec/changes/p1-s1-ingest-baseline/tasks.md

Usage:
    # Start Edge server first:
    #   conda activate old
    #   ./run_server.sh --debug

    # Then run tests:
    #   pytest tests/test_p1_s1_startup.py -v
"""

import os
import re

import pytest
import requests

BASE_URL = "http://localhost:8083"
API_V1 = f"{BASE_URL}/v1"

# Log file path - adjust if needed
DEFAULT_LOG_PATH = "/tmp/openrecall_server.log"


def get_queue_status() -> dict:
    resp = requests.get(f"{API_V1}/ingest/queue/status", timeout=5)
    resp.raise_for_status()
    return resp.json()


def get_health() -> dict:
    resp = requests.get(f"{API_V1}/health", timeout=5)
    resp.raise_for_status()
    return resp.json()


class TestStartupBasicVerification:
    """Tests for Section 11: Startup and Basic Verification."""

    @pytest.mark.integration
    def test_11_2_queue_status_returns_noop_mode(self):
        """
        11.2 Call GET /v1/ingest/queue/status and confirm processing_mode is 'noop'.

        Requires: Running Edge server.
        """
        status = get_queue_status()
        assert status["processing_mode"] == "noop", (
            f"Expected 'noop', got {status['processing_mode']}"
        )

    @pytest.mark.integration
    def test_11_3_health_status_enum(self):
        """
        11.3 P1-S1 health status enumeration: status should be only 'ok' or 'degraded', never 'error'.

        Test in both empty DB and after ingest scenarios.
        Requires: Running Edge server.
        """
        health = get_health()
        assert "status" in health, "Health response missing 'status' field"

        valid_statuses = {"ok", "degraded"}
        assert health["status"] in valid_statuses, (
            f"Health status '{health['status']}' is not valid for P1-S1. "
            f"Expected one of {valid_statuses}"
        )

        status = get_queue_status()
        if status["pending"] + status["completed"] > 0:
            health2 = get_health()
            assert health2["status"] in valid_statuses, (
                f"Health status '{health2['status']}' is not valid for P1-S1"
            )


class TestManualStartup:
    """Manual tests - can verify by reading log file."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.log_path = os.environ.get("OPENRECALL_LOG_PATH", DEFAULT_LOG_PATH)
        yield

    @pytest.mark.integration
    def test_11_1_server_startup_log_noop(self):
        """
        11.1 Verify startup log shows 'MRV3 processing_mode=noop' exactly once.

        Also verify NO OCR/provider/model preload logs appear.

        Requires: Server log file accessible.
        """
        if not os.path.exists(self.log_path):
            pytest.skip(f"Log file not found: {self.log_path}")

        with open(self.log_path, "r") as f:
            log_content = f.read()

        # Count occurrences of MRV3 processing_mode=noop
        count = log_content.count("MRV3 processing_mode=noop")
        assert count == 1, (
            f"Expected 1 occurrence of 'MRV3 processing_mode=noop', found {count}"
        )

        # Verify NO OCR/AI/Model preload logs
        preload_patterns = [
            r"preload.*model",
            r"loading.*ocr",
            r"loading.*ai",
            r"vision.*model.*load",
        ]
        for pattern in preload_patterns:
            matches = re.findall(pattern, log_content, re.IGNORECASE)
            assert len(matches) == 0, (
                f"Found preload logs that should not appear in noop mode: {matches}"
            )

    @pytest.mark.integration
    def test_11_4_lifecycle_single_anchor(self):
        """
        11.4 Verify 'MRV3 processing_mode=noop' appears exactly once per process.

        This is the same as 11.1 - the anchor appears once per server process.
        """
        if not os.path.exists(self.log_path):
            pytest.skip(f"Log file not found: {self.log_path}")

        with open(self.log_path, "r") as f:
            log_content = f.read()

        count = log_content.count("MRV3 processing_mode=noop")
        assert count == 1, f"Expected 1 occurrence, found {count}"

    @pytest.mark.integration
    def test_11_5_migration_log_anchor(self):
        """
        11.5 Verify 'v3 schema migrations ensured' log appears before NoopQueueDriver and health queries.

        Migration must complete before queue driver starts processing.
        """
        if not os.path.exists(self.log_path):
            pytest.skip(f"Log file not found: {self.log_path}")

        with open(self.log_path, "r") as f:
            lines = f.readlines()

        # Find line numbers
        migration_line = None
        noop_line = None
        health_line = None

        for i, line in enumerate(lines):
            if "v3 schema migrations ensured" in line:
                migration_line = i
            if "MRV3 processing_mode=noop" in line:
                noop_line = i
            if "GET /v1/health HTTP" in line:
                if health_line is None:
                    health_line = i

        assert migration_line is not None, "Migration log not found"
        assert noop_line is not None, "NoopQueueDriver log not found"

        # Migration must come before NoopQueueDriver
        assert migration_line < noop_line, (
            f"Migration (line {migration_line}) must come before NoopQueueDriver (line {noop_line})"
        )

        # Migration should come before first health query
        if health_line is not None:
            assert migration_line < health_line, (
                f"Migration (line {migration_line}) must come before health query (line {health_line})"
            )
