# openrecall/server/embedding/service.py
"""Embedding service: enqueue, generate, backfill."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.embedding.providers import (
    MultimodalEmbeddingProvider,
)

if TYPE_CHECKING:
    from openrecall.server.database.frames_store import FramesStore
    from openrecall.server.database.embedding_store import EmbeddingStore

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min
_MAX_RETRIES = 3


class EmbeddingService:
    """Service for frame embedding operations."""

    def __init__(
        self,
        store: "FramesStore",
        embedding_store: Optional["EmbeddingStore"] = None,
        provider: Optional[MultimodalEmbeddingProvider] = None,
    ) -> None:
        self._store = store
        self._embedding_store = embedding_store
        self._provider = provider

    @property
    def embedding_store(self) -> "EmbeddingStore":
        if self._embedding_store is None:
            from openrecall.server.database.embedding_store import EmbeddingStore
            self._embedding_store = EmbeddingStore()
        return self._embedding_store

    @property
    def provider(self) -> MultimodalEmbeddingProvider:
        if self._provider is None:
            from openrecall.server.ai.factory import get_multimodal_embedding_provider
            self._provider = get_multimodal_embedding_provider()
        return self._provider

    def enqueue_embedding_task(self, conn, frame_id: int) -> None:
        """Insert a pending embedding task for a frame. Idempotent."""
        try:
            conn.execute(
                """
                INSERT INTO embedding_tasks (frame_id, status)
                VALUES (?, 'pending')
                """,
                (frame_id,),
            )
            conn.execute(
                """
                UPDATE frames SET embedding_status = 'pending'
                WHERE id = ? AND embedding_status IS NULL
                """,
                (frame_id,),
            )
            conn.commit()
            logger.debug(f"Embedding task enqueued for frame #{frame_id}")
        except Exception as e:
            # Likely duplicate - ignore
            logger.debug(f"Failed to enqueue embedding task: {e}")

    def generate_embedding(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> FrameEmbedding:
        """Call the embedding provider to generate an embedding."""
        vector = self.provider.embed_image(image_path, text)
        return FrameEmbedding(
            frame_id=0,  # Will be set by caller
            embedding_vector=vector.tolist(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def save_embedding(
        self,
        conn,
        frame_id: int,
        embedding: FrameEmbedding,
        timestamp: str,
        app_name: str = "",
        window_name: str = "",
    ) -> None:
        """Save embedding to LanceDB."""
        embedding.frame_id = frame_id
        embedding.timestamp = timestamp
        embedding.app_name = app_name
        embedding.window_name = window_name
        self.embedding_store.save_embedding(embedding)

    def mark_completed(self, conn, task_id: int, frame_id: int) -> None:
        """Mark an embedding task as completed."""
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE embedding_tasks
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (now, task_id),
        )
        conn.execute(
            """
            UPDATE frames SET embedding_status = 'completed'
            WHERE id = ?
            """,
            (frame_id,),
        )
        conn.commit()
        # Try to mark as queryable if all stages are complete
        self._store.try_set_queryable(conn, frame_id)

    def mark_failed(
        self,
        conn,
        task_id: int,
        frame_id: int,
        error_message: str,
        retry_count: int,
    ) -> None:
        """Mark an embedding task as failed or schedule retry."""
        if retry_count < _MAX_RETRIES:
            delay_seconds = _RETRY_DELAYS[retry_count - 1]
            next_retry = datetime.now(timezone.utc).replace(microsecond=0)
            next_retry = next_retry + timedelta(seconds=delay_seconds)
            conn.execute(
                """
                UPDATE embedding_tasks
                SET retry_count = ?, next_retry_at = ?, error_message = ?
                WHERE id = ?
                """,
                (retry_count + 1, next_retry.isoformat(), error_message, task_id),
            )
            logger.info(
                f"Embedding task #{task_id} failed (retry {retry_count}/{_MAX_RETRIES}), "
                f"rescheduled at {next_retry.isoformat()}"
            )
        else:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE embedding_tasks
                SET status = 'failed', error_message = ?, failed_at = ?
                WHERE id = ?
                """,
                (error_message, now, task_id),
            )
            conn.execute(
                """
                UPDATE frames SET embedding_status = 'failed'
                WHERE id = ?
                """,
                (frame_id,),
            )
            # Mark visibility_status as failed
            self._store.try_set_failed(conn, frame_id)
            logger.error(
                f"Embedding task #{task_id} permanently failed for frame #{frame_id}: {error_message}"
            )
        conn.commit()

    def get_queue_status(self, conn) -> dict[str, int]:
        """Return queue statistics."""
        rows = conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM embedding_tasks
            GROUP BY status
            """
        ).fetchall()
        result = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        for row in rows:
            status = row[0]
            count = row[1]
            if status in result:
                result[status] = count
        return result

    def backfill(self, conn) -> int:
        """Enqueue all frames without embedding_status. Returns count."""
        cursor = conn.execute(
            """
            INSERT INTO embedding_tasks (frame_id, status)
            SELECT id, 'pending' FROM frames
            WHERE embedding_status IS NULL
              AND id NOT IN (SELECT frame_id FROM embedding_tasks)
            """
        )
        conn.commit()
        return cursor.rowcount
