"""Background worker for frame description generation."""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Optional

from openrecall.server.description.models import FrameContext
from openrecall.server.description.service import DescriptionService
from openrecall.server.description.providers import DescriptionProviderError

if TYPE_CHECKING:
    from openrecall.server.database.frames_store import FramesStore

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0  # seconds
_STATS_INTERVAL = 60.0  # seconds, queue status log interval


class DescriptionWorker(threading.Thread):
    """Background worker thread that processes pending description tasks."""

    def __init__(self, store: "FramesStore", poll_interval: float = _POLL_INTERVAL):
        super().__init__(daemon=True, name="DescriptionWorker")
        self._store = store
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._service: Optional[DescriptionService] = None
        self._last_processing_version: int = -1  # NEW; -1 forces first-batch alignment
        self._stats_counter = 0
        self._last_stats_time = 0.0

    @property
    def service(self) -> DescriptionService:
        if self._service is None:
            self._service = DescriptionService(store=self._store)
        return self._service

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("DescriptionWorker started")
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
        logger.info("DescriptionWorker stopped")

    def _log_queue_status(self, conn: sqlite3.Connection) -> None:
        """Log queue statistics periodically."""
        now = time.time()
        if now - self._last_stats_time >= _STATS_INTERVAL:
            try:
                status = self.service.get_queue_status(conn)
                logger.info(
                    f"Description queue stats: pending={status.get('pending', 0)}, "
                    f"processing={status.get('processing', 0)}, "
                    f"failed={status.get('failed', 0)}"
                )
            except Exception as e:
                logger.debug(f"Failed to get queue status: {e}")
            self._last_stats_time = now

    def _process_batch(self, conn: sqlite3.Connection) -> None:
        """Fetch and process one pending description task."""
        from openrecall.server.config_runtime import runtime_settings
        current_version = runtime_settings.ai_processing_version
        if current_version != self._last_processing_version:
            if self._service is not None:
                logger.info(
                    f"DescriptionWorker rebuilding service (version "
                    f"{self._last_processing_version} -> {current_version})"
                )
            self._service = None
            self._last_processing_version = current_version

        # Log queue status periodically
        self._log_queue_status(conn)

        task = self._store.claim_description_task(conn)
        if task is None:
            logger.debug("No pending description tasks")
            return

        task_id, frame_id = task["id"], task["frame_id"]
        logger.debug(f"Processing description task #{task_id} for frame #{frame_id}")

        # Pass conn to reuse the connection
        frame = self._store.get_frame_by_id(frame_id, conn)
        if frame is None:
            logger.warning(f"Frame #{frame_id} not found, skipping task #{task_id}")
            return

        snapshot_path = frame.get("snapshot_path")
        if not snapshot_path:
            logger.warning(f"Frame #{frame_id} has no snapshot_path, skipping")
            self.service.mark_failed(conn, task_id, frame_id, "No snapshot_path", 1)
            return

        context = FrameContext(
            app_name=frame.get("app_name"),
            window_name=frame.get("window_name"),
            browser_url=frame.get("browser_url"),
        )

        try:
            description = self.service.generate_description(snapshot_path, context)
            self.service.insert_description(conn, frame_id, description)
            self.service.mark_completed(conn, task_id, frame_id)
            logger.info(f"Description completed for frame #{frame_id}")
        except DescriptionProviderError as e:
            retry_count = task.get("retry_count", 0) + 1
            self.service.mark_failed(conn, task_id, frame_id, str(e), retry_count)
        except Exception as e:
            logger.error(f"Unexpected error processing frame #{frame_id}: {e}")
            retry_count = task.get("retry_count", 0) + 1
            self.service.mark_failed(conn, task_id, frame_id, str(e), retry_count)
