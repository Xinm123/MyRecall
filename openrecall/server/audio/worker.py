"""Background worker for processing audio chunks asynchronously."""

import logging
import sqlite3
import threading
import traceback

from openrecall.server.database import SQLStore
from openrecall.server.audio.processor import AudioChunkProcessor
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class AudioProcessingWorker(threading.Thread):
    """Background worker that processes PENDING audio chunks.

    Follows the same pattern as VideoProcessingWorker:
    - Thread-isolated SQLite connection
    - Daemon thread with stop event
    - Reset stuck chunks on startup
    - Poll loop with sleep when idle (5s vs 2s for video)
    """

    def __init__(self):
        super().__init__(daemon=True, name="AudioProcessingWorker")
        self._stop_event = threading.Event()
        logger.info("🎧 [AUDIO-SERVER] AudioProcessingWorker initialized")

    def stop(self):
        """Signal the worker to stop."""
        logger.info("🎧 [AUDIO-SERVER] AudioProcessingWorker stop signal received")
        self._stop_event.set()

    def run(self):
        """Main processing loop."""
        logger.info("🎧 [AUDIO-SERVER] AudioProcessingWorker started")

        sql_store = SQLStore()
        processor = AudioChunkProcessor(sql_store=sql_store)

        # Thread-isolated connection for status updates
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute("PRAGMA journal_mode=WAL")

        try:
            # Reset stuck chunks from previous crash
            count = sql_store.reset_stuck_audio_chunks(conn)
            if count > 0:
                logger.warning(
                    f"Recovered {count} stuck audio chunks from previous session"
                )

            while not self._stop_event.is_set():
                chunk_id = None
                try:
                    chunk = sql_store.get_next_pending_audio_chunk(conn)

                    if chunk is None:
                        self._stop_event.wait(
                            5.0
                        )  # 5s poll interval (lower priority than video)
                        continue

                    chunk_id = chunk["id"]
                    chunk_path = chunk["file_path"]
                    chunk_timestamp = float(chunk.get("timestamp", 0))
                    device_name = chunk.get("device_name", "unknown")

                    logger.info(
                        "🎧 [AUDIO-SERVER] Processing chunk | id=%d | device=%s | path=%s",
                        chunk_id,
                        device_name,
                        chunk_path,
                    )

                    # Mark as PROCESSING
                    if not sql_store.mark_audio_chunk_processing(conn, chunk_id):
                        self._stop_event.wait(0.5)
                        continue

                    # Process the chunk
                    result = processor.process_chunk(
                        chunk_id, chunk_path, chunk_timestamp
                    )

                    # Mark as COMPLETED or FAILED
                    if result.error:
                        sql_store.mark_audio_chunk_failed(conn, chunk_id)
                        logger.error(
                            "🎧 [AUDIO-SERVER] ❌ Chunk %d failed: %s",
                            chunk_id,
                            result.error,
                        )
                    else:
                        sql_store.mark_audio_chunk_completed(conn, chunk_id)
                        if result.transcriptions_count == 0:
                            logger.info(
                                "🎧 [AUDIO-SERVER] Chunk completed with no transcriptions | id=%d | no_transcription_reason=%s",
                                chunk_id,
                                result.no_transcription_reason or "unknown",
                            )

                except Exception as e:
                    logger.error(f"Error in audio worker loop: {e}")
                    logger.error(traceback.format_exc())
                    # Mark chunk as FAILED if we were processing one
                    if chunk_id is not None:
                        try:
                            sql_store.mark_audio_chunk_failed(conn, chunk_id)
                        except Exception:
                            pass
                    self._stop_event.wait(1.0)

        finally:
            conn.close()
            logger.info(
                "🎧 [AUDIO-SERVER] AudioProcessingWorker stopped and connection closed"
            )
