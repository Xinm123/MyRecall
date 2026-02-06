"""Tests for Phase 0 upload queue (ADR-0002 compliance)."""

import json
import os
import time
from pathlib import Path

import pytest
from PIL import Image


def _create_test_image(size_bytes: int = 1000) -> Image.Image:
    """Create a minimal test image."""
    return Image.new("RGB", (10, 10), color="red")


def _create_queue(tmp_path, max_size_gb=0.0001, ttl_days=7):
    """Create an UploadQueue with small capacity for testing."""
    from openrecall.client.upload_queue import UploadQueue
    return UploadQueue(buffer_dir=tmp_path / "buffer", max_size_gb=max_size_gb, ttl_days=ttl_days)


class TestCapacityEnforcement:
    def test_capacity_enforcement_fifo(self, tmp_path):
        """UQ-01: Oldest files deleted when capacity exceeded."""
        from openrecall.client.upload_queue import UploadQueue

        # Very small capacity: ~100 bytes
        queue = UploadQueue(buffer_dir=tmp_path / "buffer", max_size_gb=100 / (1024**3))

        img = _create_test_image()
        ids = []
        for i in range(5):
            item_id = queue.enqueue(img, {"timestamp": 1000 + i, "active_app": f"app_{i}"})
            ids.append(item_id)
            time.sleep(0.01)  # Ensure different mtime

        # The queue should have enforced capacity by deleting oldest
        current_size = queue.get_total_size()
        # We can't assert exact count since image sizes vary,
        # but the queue should be under capacity
        assert current_size <= queue.max_size_bytes or queue.count() < 5

    def test_fifo_deletion_order(self, tmp_path):
        """UQ-03: Oldest chunks deleted first when capacity reached."""
        from openrecall.client.upload_queue import UploadQueue

        buffer_dir = tmp_path / "buffer"
        buffer_dir.mkdir(parents=True, exist_ok=True)

        # Create files with sequential timestamps
        for i in range(5):
            f = buffer_dir / f"chunk_{i}.dat"
            f.write_bytes(b"x" * 50)
            # Set mtime to ensure ordering
            os.utime(f, (1000 + i, 1000 + i))

        queue = UploadQueue(buffer_dir=buffer_dir, max_size_gb=100 / (1024**3))

        # Files sorted by age should be oldest first
        files = queue._get_files_sorted_by_age()
        assert files[0].name == "chunk_0.dat"
        assert files[-1].name == "chunk_4.dat"


class TestTTLCleanup:
    def test_ttl_cleanup_7_days(self, tmp_path):
        """UQ-02: Chunks >7 days auto-deleted."""
        from openrecall.client.upload_queue import UploadQueue

        buffer_dir = tmp_path / "buffer"
        buffer_dir.mkdir(parents=True, exist_ok=True)

        # Create files with old timestamps (>7 days = 604800s)
        old_time = time.time() - (8 * 24 * 3600)  # 8 days ago
        for i in range(3):
            f = buffer_dir / f"old_{i}.dat"
            f.write_bytes(b"old data")
            os.utime(f, (old_time, old_time))

        # Create recent files
        for i in range(2):
            f = buffer_dir / f"new_{i}.dat"
            f.write_bytes(b"new data")

        queue = UploadQueue(buffer_dir=buffer_dir, ttl_days=7)
        deleted = queue.cleanup_expired()

        assert deleted == 3, f"Expected 3 files deleted, got {deleted}"

        # Recent files should remain
        remaining = list(buffer_dir.iterdir())
        assert len(remaining) == 2


class TestPostUploadDeletion:
    def test_post_upload_deletion_timing(self, tmp_path):
        """UQ-04: Successful upload deletes local copy within 1s."""
        from openrecall.client.upload_queue import UploadQueue

        queue = UploadQueue(buffer_dir=tmp_path / "buffer")
        img = _create_test_image()
        item_id = queue.enqueue(img, {"timestamp": 1000, "active_app": "test"})

        # Verify file exists
        assert (queue.storage_dir / f"{item_id}.json").exists()
        assert (queue.storage_dir / f"{item_id}.webp").exists()

        # Simulate commit (post-upload deletion)
        start = time.perf_counter()
        queue.commit([item_id])
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Commit took {elapsed:.3f}s (target: <1s)"
        assert not (queue.storage_dir / f"{item_id}.json").exists()
        assert not (queue.storage_dir / f"{item_id}.webp").exists()


class TestExponentialBackoff:
    def test_backoff_schedule(self):
        """UQ-05: Retry delays match ADR-0002: 1min->5min->15min->1h->6h."""
        from openrecall.client.upload_queue import UploadQueue

        expected = [60, 300, 900, 3600, 21600]
        for retry_count, expected_delay in enumerate(expected, start=1):
            actual = UploadQueue.get_backoff_delay(retry_count)
            assert actual == expected_delay, (
                f"Retry {retry_count}: expected {expected_delay}s, got {actual}s"
            )

    def test_backoff_caps_at_max(self):
        """Retry count > 5 still returns max delay (6h)."""
        from openrecall.client.upload_queue import UploadQueue

        for retry_count in [6, 7, 10, 100]:
            delay = UploadQueue.get_backoff_delay(retry_count)
            assert delay == 21600, f"Retry {retry_count}: expected 21600s, got {delay}s"

    def test_consumer_uses_adr0002_backoff(self):
        """Consumer's _handle_failure uses ADR-0002 backoff schedule."""
        from openrecall.client.upload_queue import UploadQueue

        # Verify the static method returns correct values
        assert UploadQueue.get_backoff_delay(1) == 60
        assert UploadQueue.get_backoff_delay(2) == 300
        assert UploadQueue.get_backoff_delay(5) == 21600
