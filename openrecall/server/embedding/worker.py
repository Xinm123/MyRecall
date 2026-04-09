"""Background worker for frame embedding generation."""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from openrecall.server.database.frames_store import FramesStore

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0  # seconds
_STATS_INTERVAL = 60.0  # seconds


class EmbeddingWorker(threading.Thread):
    """Background worker thread that processes pending embedding tasks."""

    def __init__(
        self,
        store: "FramesStore",
        poll_interval: float = _POLL_INTERVAL,
    ):
        super().__init__(daemon=True, name="EmbeddingWorker")
        self._store = store
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._service = None
        self._last_stats_time = 0.0

    @property
    def service(self):
        if self._service is None:
            from openrecall.server.embedding.service import EmbeddingService
            self._service = EmbeddingService(store=self._store)
        return self._service

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("EmbeddingWorker started")
        while not self._stop_event.is_set():
            try:
                with self._store._connect() as conn:
                    self._process_batch(conn)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    logger.warning("Database locked, will retry")
                else:
                    logger.error(f"Database error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}")
            self._stop_event.wait(timeout=self._poll_interval)
        logger.info("EmbeddingWorker stopped")

    def _log_queue_status(self, conn: sqlite3.Connection) -> None:
        """Log queue statistics periodically."""
        now = time.time()
        if now - self._last_stats_time >= _STATS_INTERVAL:
            try:
                status = self.service.get_queue_status(conn)
                logger.info(
                    f"Embedding queue stats: pending={status.get('pending', 0)}, "
                    f"processing={status.get('processing', 0)}, "
                    f"failed={status.get('failed', 0)}"
                )
            except Exception as e:
                logger.debug(f"Failed to get queue status: {e}")
            self._last_stats_time = now

    def _process_batch(self, conn: sqlite3.Connection) -> None:
        """Fetch and process one pending embedding task."""
        self._log_queue_status(conn)

        task = self._store.claim_embedding_task(conn)
        if task is None:
            logger.debug("No pending embedding tasks")
            return

        task_id, frame_id = task["id"], task["frame_id"]
        logger.debug(f"Processing embedding task #{task_id} for frame #{frame_id}")

        frame = self._store.get_frame_by_id(frame_id, conn)
        if frame is None:
            logger.warning(f"Frame #{frame_id} not found, skipping task #{task_id}")
            return

        snapshot_path = frame.get("snapshot_path")
        if not snapshot_path:
            logger.warning(f"Frame #{frame_id} has no snapshot_path, skipping")
            self.service.mark_failed(conn, task_id, frame_id, "No snapshot_path", 1)
            return

        try:
            embedding = self.service.generate_embedding(
                image_path=snapshot_path,
                text=frame.get("full_text"),
            )
            self.service.save_embedding(
                conn,
                frame_id,
                embedding,
                timestamp=frame.get("timestamp", ""),
                app_name=frame.get("app_name", ""),
                window_name=frame.get("window_name", ""),
            )
            self.service.mark_completed(conn, task_id, frame_id)
            logger.info(f"Embedding completed for frame #{frame_id}")
        except Exception as e:
            logger.error(f"Embedding generation failed for frame #{frame_id}: {e}")
            retry_count = task.get("retry_count", 0) + 1
            self.service.mark_failed(conn, task_id, frame_id, str(e), retry_count)
