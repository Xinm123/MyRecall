"""Background worker for processing video chunks asynchronously."""

import logging
import sqlite3
import threading
import traceback

from openrecall.server.database import SQLStore
from openrecall.server.video.processor import VideoChunkProcessor
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class VideoProcessingWorker(threading.Thread):
    """Background worker that processes PENDING video chunks.

    Follows the same pattern as ProcessingWorker:
    - Thread-isolated SQLite connection
    - Daemon thread with stop event
    - Reset stuck chunks on startup
    - Poll loop with sleep when idle
    """

    def __init__(self):
        super().__init__(daemon=True, name="VideoProcessingWorker")
        self._stop_event = threading.Event()
        logger.info("📹 [VIDEO-SERVER] VideoProcessingWorker initialized")

    def stop(self):
        """Signal the worker to stop."""
        logger.info("📹 [VIDEO-SERVER] VideoProcessingWorker stop signal received")
        self._stop_event.set()

    def run(self):
        """Main processing loop."""
        logger.info("📹 [VIDEO-SERVER] VideoProcessingWorker started")

        sql_store = SQLStore()
        processor = VideoChunkProcessor(sql_store=sql_store)

        # Thread-isolated connection for status updates
        conn = sqlite3.connect(str(settings.db_path))

        try:
            # Reset stuck chunks from previous crash
            count = sql_store.reset_stuck_video_chunks(conn)
            if count > 0:
                logger.warning(
                    f"Recovered {count} stuck video chunks from previous session"
                )

            while not self._stop_event.is_set():
                try:
                    chunk = sql_store.get_next_pending_video_chunk(conn)

                    if chunk is None:
                        self._stop_event.wait(2.0)
                        continue

                    chunk_id = chunk["id"]
                    chunk_path = chunk["file_path"]

                    # Phase 1.5: Use stored start_time if available, fallback to created_at
                    chunk_start_time = chunk.get("start_time")
                    if chunk_start_time is None:
                        chunk_start_time = 0.0
                        try:
                            import datetime

                            dt = datetime.datetime.fromisoformat(chunk["created_at"])
                            chunk_start_time = dt.timestamp()
                        except Exception:
                            pass

                    logger.info(
                        "📹 [VIDEO-SERVER] Processing chunk | id=%d | path=%s",
                        chunk_id,
                        chunk_path,
                    )

                    # Mark as PROCESSING
                    if not sql_store.mark_video_chunk_processing(conn, chunk_id):
                        self._stop_event.wait(0.5)
                        continue

                    # Process the chunk
                    result = processor.process_chunk(
                        chunk_id, chunk_path, chunk_start_time
                    )

                    # Mark as COMPLETED or FAILED
                    if result.error:
                        sql_store.mark_video_chunk_failed(conn, chunk_id)
                        logger.error(
                            "📹 [VIDEO-SERVER] ❌ Chunk %d failed: %s",
                            chunk_id,
                            result.error,
                        )
                    else:
                        sql_store.mark_video_chunk_completed(conn, chunk_id)

                except Exception as e:
                    logger.error(f"Error in video worker loop: {e}")
                    logger.error(traceback.format_exc())
                    self._stop_event.wait(1.0)

        finally:
            conn.close()
            logger.info(
                "📹 [VIDEO-SERVER] VideoProcessingWorker stopped and connection closed"
            )
