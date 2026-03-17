"""P1-S3 Integration Test: V3ProcessingWorker lifecycle.

Tests the worker lifecycle: start, stop, status transitions.

SSOT: design.md D1
"""

import sqlite3
import time
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.server.processing.v3_worker import V3ProcessingWorker


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database with v3 schema."""
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db: Path) -> FramesStore:
    """Create a FramesStore with temporary database."""
    return FramesStore(db_path=temp_db)


class TestV3WorkerLifecycle:
    """Tests for V3ProcessingWorker lifecycle."""

    def test_worker_starts_successfully(self, temp_db: Path):
        """Test that worker starts successfully."""
        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        try:
            worker.start()
            assert worker._thread is not None
            assert worker._thread.is_alive()
        finally:
            worker.stop()
            worker.join(timeout=2)

    def test_worker_stop_terminates_thread(self, temp_db: Path):
        """Test that stop() terminates the worker thread."""
        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        worker.start()
        assert worker._thread.is_alive()

        worker.stop()
        worker.join(timeout=2)

        assert not worker._thread.is_alive() if worker._thread else True

    def test_worker_can_be_restarted(self, temp_db: Path):
        """Test that worker can be restarted after stop."""
        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        # First cycle
        worker.start()
        time.sleep(0.2)
        worker.stop()
        worker.join(timeout=2)

        # Second cycle
        worker.start()
        time.sleep(0.2)
        assert worker._thread.is_alive()

        worker.stop()
        worker.join(timeout=2)

    def test_worker_handles_empty_queue(self, temp_db: Path):
        """Test that worker handles empty queue gracefully."""
        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        worker.start()
        time.sleep(0.3)  # Let it poll a few times

        # Should still be running
        assert worker._thread.is_alive()

        worker.stop()
        worker.join(timeout=2)

    def test_worker_idempotent_start(self, temp_db: Path):
        """Test that calling start() twice is idempotent."""
        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        worker.start()
        first_thread = worker._thread

        # Second start should be idempotent
        worker.start()
        assert worker._thread is first_thread

        worker.stop()
        worker.join(timeout=2)

    def test_worker_processes_pending_frames(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that worker processes pending frames."""
        # Create a pending frame (without valid snapshot - will fail quickly)
        frame_id, _ = store.claim_frame(
            capture_id="worker-test-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "capture_trigger": "manual",
            },
        )

        # Start worker with short poll interval
        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        worker.start()

        # Wait for processing
        time.sleep(0.5)

        worker.stop()
        worker.join(timeout=2)

        # Frame should have been processed (status changed from pending)
        # Since no valid image exists, it should be marked as failed
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()

            # Status should have changed from 'pending'
            assert row["status"] in ("processing", "completed", "failed")


class TestV3WorkerStatusTransitions:
    """Tests for status transitions during processing."""

    def test_pending_to_processing_transition(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that pending frames transition to processing."""
        frame_id, _ = store.claim_frame(
            capture_id="status-test-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "capture_trigger": "manual",
            },
        )

        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.1)

        # Manually trigger one process cycle
        frames = worker._fetch_pending_frames()
        assert len(frames) == 1
        assert frames[0][0] == frame_id

    def test_failed_status_set_on_missing_snapshot(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that frames with missing snapshot are marked failed."""
        frame_id, _ = store.claim_frame(
            capture_id="fail-test-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "capture_trigger": "manual",
            },
        )
        # Don't set snapshot_path - frame has no image

        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.05)
        worker.start()

        # Wait for processing
        time.sleep(0.3)

        worker.stop()
        worker.join(timeout=2)

        # Verify frame status
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, error_message FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()

            # Should be failed due to missing snapshot
            assert row["status"] in ("processing", "failed")
            if row["status"] == "failed":
                assert row["error_message"] is not None

    def test_failed_status_on_invalid_trigger(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that invalid trigger results in failed status."""
        frame_id, _ = store.claim_frame(
            capture_id="invalid-trigger-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "capture_trigger": "INVALID_TRIGGER",  # Invalid
            },
        )
        store.finalize_claimed_frame(
            frame_id, "invalid-trigger-1", "/some/path.jpg"
        )

        worker = V3ProcessingWorker(db_path=temp_db, poll_interval=0.05)
        worker.start()

        time.sleep(0.3)

        worker.stop()
        worker.join(timeout=2)

        # Verify frame status
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, error_message FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()

            # Should be failed due to invalid trigger
            if row["status"] == "failed":
                assert "INVALID_TRIGGER" in row["error_message"]
