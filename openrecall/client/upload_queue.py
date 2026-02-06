"""Upload queue with ADR-0002 compliance for MyRecall client.

Wraps LocalBuffer with capacity enforcement, TTL cleanup,
FIFO deletion, and exponential backoff scheduling.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from PIL import Image

from openrecall.client.buffer import LocalBuffer, BufferItem
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

# ADR-0002 backoff schedule: 1min, 5min, 15min, 1h, 6h
BACKOFF_SCHEDULE = [60, 300, 900, 3600, 21600]


class UploadQueue:
    """ADR-0002 compliant upload queue with capacity, TTL, and FIFO enforcement.

    Wraps LocalBuffer and adds:
    - Maximum capacity enforcement (default 100GB)
    - TTL cleanup (default 7 days)
    - FIFO deletion when capacity exceeded
    - Immediate post-upload deletion
    - Exponential backoff schedule
    """

    def __init__(
        self,
        buffer_dir: Optional[Path] = None,
        max_size_gb: float = 100,
        ttl_days: int = 7,
    ):
        self.buffer = LocalBuffer(storage_dir=buffer_dir)
        self.max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)
        self.ttl_seconds = ttl_days * 24 * 3600
        self.storage_dir = self.buffer.storage_dir

    def enqueue(self, image: Image.Image, metadata: Dict[str, Any]) -> str:
        """Add an image to the queue, enforcing capacity limits."""
        item_id = self.buffer.enqueue(image, metadata)
        self._enforce_capacity()
        return item_id

    def commit(self, file_ids: List[str]) -> None:
        """Delete successfully uploaded items (immediate post-upload deletion)."""
        self.buffer.commit(file_ids)

    def count(self) -> int:
        """Get number of items in the queue."""
        return self.buffer.count()

    def get_next_batch(self, limit: int = 1) -> List[BufferItem]:
        """Get next batch of items (FIFO order)."""
        return self.buffer.get_next_batch(limit=limit)

    def get_total_size(self) -> int:
        """Get total size of all files in buffer directory in bytes."""
        total = 0
        if self.storage_dir.exists():
            for f in self.storage_dir.iterdir():
                if f.is_file():
                    total += f.stat().st_size
        return total

    def _get_files_sorted_by_age(self) -> List[Path]:
        """Get all files sorted by modification time (oldest first = FIFO)."""
        if not self.storage_dir.exists():
            return []
        files = [f for f in self.storage_dir.iterdir() if f.is_file()]
        files.sort(key=lambda f: f.stat().st_mtime)
        return files

    def _enforce_capacity(self) -> int:
        """Delete oldest files (FIFO) until under capacity.

        Returns:
            Number of files deleted.
        """
        deleted = 0
        while self.get_total_size() > self.max_size_bytes:
            files = self._get_files_sorted_by_age()
            if not files:
                break

            # Delete the oldest file
            oldest = files[0]
            try:
                oldest.unlink()
                deleted += 1
                logger.debug(f"Capacity enforcement: deleted {oldest.name}")

                # Also delete paired file (.json <-> .webp)
                stem = oldest.stem
                if oldest.suffix == ".json":
                    pair = self.storage_dir / f"{stem}.webp"
                elif oldest.suffix == ".webp":
                    pair = self.storage_dir / f"{stem}.json"
                else:
                    pair = None

                if pair and pair.exists():
                    pair.unlink()
                    deleted += 1

            except OSError as e:
                logger.error(f"Failed to delete {oldest}: {e}")
                break

        if deleted:
            logger.info(f"Capacity enforcement: deleted {deleted} files (FIFO)")

        return deleted

    def cleanup_expired(self) -> int:
        """Delete files older than TTL.

        Returns:
            Number of files deleted.
        """
        now = time.time()
        cutoff = now - self.ttl_seconds
        deleted = 0

        if not self.storage_dir.exists():
            return 0

        for f in sorted(self.storage_dir.iterdir()):
            if not f.is_file():
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
                    logger.debug(f"TTL cleanup: deleted {f.name}")
            except OSError as e:
                logger.error(f"TTL cleanup failed for {f}: {e}")

        if deleted:
            logger.info(f"TTL cleanup: deleted {deleted} expired files")

        return deleted

    @staticmethod
    def get_backoff_delay(retry_count: int) -> int:
        """Get backoff delay for a given retry count.

        ADR-0002 schedule: 1min -> 5min -> 15min -> 1h -> 6h

        Args:
            retry_count: Number of retries (0-based, but 0 means first failure).

        Returns:
            Delay in seconds.
        """
        idx = min(max(retry_count - 1, 0), len(BACKOFF_SCHEDULE) - 1)
        return BACKOFF_SCHEDULE[idx]
