"""Description service: enqueue, generate, backfill."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers import DescriptionProviderError
from openrecall.server.ai.factory import get_description_provider
from openrecall.shared.config import settings

if TYPE_CHECKING:
    from openrecall.server.description.providers.base import DescriptionProvider
    from openrecall.server.database.frames_store import FramesStore

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min
_MAX_RETRIES = 3


class DescriptionService:
    """Service for frame description operations."""

    def __init__(self, store: "FramesStore") -> None:
        self._store = store
        self._provider: Optional["DescriptionProvider"] = None

    @property
    def provider(self) -> "DescriptionProvider":
        if self._provider is None:
            if not settings.description_enabled:
                raise DescriptionProviderError("Description generation is disabled")
            self._provider = get_description_provider()
            logger.info(f"DescriptionProvider initialized: {type(self._provider).__name__}")
        return self._provider

    def enqueue_description_task(self, conn, frame_id: int) -> None:
        """Insert a pending description task for a frame. Idempotent."""
        self._store.insert_description_task(conn, frame_id)
        logger.debug(f"Description task enqueued for frame #{frame_id}")

    def generate_description(
        self,
        image_path: str,
        context: FrameContext,
        model_name: Optional[str] = None,
    ) -> FrameDescription:
        """Call the description provider to generate a description."""
        try:
            desc = self.provider.generate(image_path, context)
            logger.debug(
                f"Generated description: {len(desc.narrative)} chars, "
                f"{len(desc.tags)} tags"
            )
            return desc
        except Exception as e:
            logger.warning(f"Description generation failed: {e}")
            raise

    def insert_description(
        self,
        conn,
        frame_id: int,
        description: FrameDescription,
        model_name: Optional[str] = None,
    ) -> None:
        """Insert completed description into frame_descriptions."""
        db_dict = description.to_db_dict()
        self._store.insert_frame_description(
            conn,
            frame_id=frame_id,
            narrative=db_dict["narrative"],
            summary=db_dict["summary"],
            tags_json=db_dict["tags_json"],
            description_model=model_name,
        )

    def mark_completed(self, conn, task_id: int, frame_id: int) -> None:
        """Mark a description task as completed."""
        self._store.complete_description_task(conn, task_id, frame_id)

    def mark_failed(
        self,
        conn,
        task_id: int,
        frame_id: int,
        error_message: str,
        retry_count: int,
    ) -> None:
        """Mark a description task as failed or schedule retry."""
        if retry_count < _MAX_RETRIES:
            delay_seconds = _RETRY_DELAYS[retry_count - 1]
            next_retry = datetime.now(timezone.utc).replace(microsecond=0)
            next_retry = next_retry + timedelta(seconds=delay_seconds)
            self._store.reschedule_description_task(
                conn, task_id, retry_count + 1, next_retry.isoformat()
            )
            logger.info(
                f"Description task #{task_id} failed (retry {retry_count}/{_MAX_RETRIES}), "
                f"rescheduled at {next_retry.isoformat()}"
            )
        else:
            self._store.fail_description_task(conn, task_id, frame_id, error_message)
            logger.warning(f"Description task #{task_id} permanently failed after {_MAX_RETRIES} retries")

    def backfill(self, conn) -> int:
        """Enqueue all frames without description_status. Returns count."""
        return self._store.enqueue_pending_descriptions(conn)

    def get_queue_status(self, conn) -> dict[str, int]:
        """Return queue statistics."""
        return self._store.get_description_queue_status(conn)
