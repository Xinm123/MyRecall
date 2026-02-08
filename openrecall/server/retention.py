"""Retention worker for automatic cleanup of expired data."""

import logging
import threading
import time
from pathlib import Path

from openrecall.server.database import SQLStore
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class RetentionWorker(threading.Thread):
    """Background daemon that periodically deletes expired data.

    Handles:
    - Expired video chunks (and CASCADE: frames, ocr_text, frame PNGs)
    - Expired screenshot entries

    Runs every `settings.retention_check_interval` seconds (default 6h).
    """

    def __init__(self):
        super().__init__(daemon=True, name="RetentionWorker")
        self._stop_event = threading.Event()
        logger.info("RetentionWorker initialized")

    def stop(self):
        """Signal the worker to stop."""
        logger.info("RetentionWorker stop signal received")
        self._stop_event.set()

    def run(self):
        """Main retention loop."""
        logger.info("RetentionWorker started")
        sql_store = SQLStore()

        while not self._stop_event.is_set():
            try:
                self._cleanup_expired_video_chunks(sql_store)
                self._cleanup_expired_entries(sql_store)
            except Exception as e:
                logger.error(f"Retention cleanup error: {e}")

            # Wait for next check interval
            self._stop_event.wait(settings.retention_check_interval)

        logger.info("RetentionWorker stopped")

    def _cleanup_expired_video_chunks(self, sql_store: SQLStore) -> None:
        """Delete expired video chunks and associated data."""
        expired = sql_store.get_expired_video_chunks()
        if not expired:
            return

        logger.info(f"Found {len(expired)} expired video chunks for cleanup")
        total_frames = 0

        for chunk in expired:
            chunk_id = chunk["id"]
            file_path = chunk.get("file_path", "")

            # Delete frame PNG files
            try:
                import sqlite3
                with sqlite3.connect(str(settings.db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM frames WHERE video_chunk_id=?", (chunk_id,))
                    frame_ids = [row["id"] for row in cursor.fetchall()]

                for frame_id in frame_ids:
                    png_path = settings.frames_path / f"{frame_id}.png"
                    if png_path.exists():
                        png_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete frame PNGs for chunk {chunk_id}: {e}")

            # Cascade delete from DB
            frames_deleted = sql_store.delete_video_chunk_cascade(chunk_id)
            total_frames += frames_deleted

            # Delete the video file
            try:
                video_file = Path(file_path)
                if video_file.exists():
                    video_file.unlink()
            except Exception as e:
                logger.error(f"Failed to delete video file {file_path}: {e}")

        logger.info(f"Retention cleanup: deleted {len(expired)} chunks, {total_frames} frames")

    def _cleanup_expired_entries(self, sql_store: SQLStore) -> None:
        """Delete expired screenshot entries."""
        expired = sql_store.get_expired_entries()
        if not expired:
            return

        logger.info(f"Found {len(expired)} expired entries for cleanup")

        for entry in expired:
            entry_id = entry.get("id")
            timestamp = entry.get("timestamp")
            try:
                # Delete screenshot file
                png_path = settings.screenshots_path / f"{timestamp}.png"
                if png_path.exists():
                    png_path.unlink()

                # Delete from DB
                import sqlite3
                with sqlite3.connect(str(settings.db_path)) as conn:
                    conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
            except Exception as e:
                logger.error(f"Failed to delete expired entry {entry_id}: {e}")

        logger.info(f"Retention cleanup: deleted {len(expired)} expired entries")
