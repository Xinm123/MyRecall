"""v3 QueueDriver: background worker that drives frame status transitions.

P1-S1 only ships ``NoopQueueDriver``, which advances every pending frame
straight to ``completed`` (optionally via ``processing`` as an intermediate
state).  No real AI processing is performed.

SSOT: tasks.md §7.1, §7.2
"""

import logging
import threading
import uuid
from typing import Optional

from openrecall.server.database.frames_store import FramesStore
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

# Valid REASON values for the Gate log anchor.
_VALID_REASONS = frozenset({"DB_WRITE_FAILED", "IO_ERROR", "STATE_MACHINE_ERROR"})

# How often the driver polls for pending frames (seconds).
_POLL_INTERVAL_SECONDS = 2.0


class NoopQueueDriver:
    """Background thread that advances pending frames to completed.

    The driver polls the ``frames`` table for rows with ``status='pending'``
    and advances each one through the state machine:

        pending → processing → completed

    When a state transition fails the driver calls
    ``FramesStore.mark_failed()`` and emits the Gate log anchor::

        MRV3 frame_failed reason=<REASON> request_id=<uuid-v4> capture_id=<uuid-v7> frame_id=<int>

    The driver runs as a daemon thread so it terminates automatically when the
    main process exits.
    """

    def __init__(
        self,
        db_path=None,
        poll_interval: float = _POLL_INTERVAL_SECONDS,
    ) -> None:
        self._store = FramesStore(db_path=db_path)
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("NoopQueueDriver.start() called but thread already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="noop-queue-driver",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "NoopQueueDriver started (poll_interval=%.1fs)", self._poll_interval
        )

    def stop(self) -> None:
        """Signal the driver to stop and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)
            self._thread = None
        logger.info("NoopQueueDriver stopped")

    def join(self, timeout: Optional[float] = None) -> None:
        """Block until the driver thread terminates."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main poll loop — runs until stop() is called."""
        logger.debug("NoopQueueDriver._run() entered")
        while not self._stop_event.is_set():
            try:
                self._process_pending_frames()
            except Exception as exc:
                # Broad catch: the loop must never die due to unexpected errors.
                logger.exception(
                    "NoopQueueDriver: unexpected error in poll loop: %s", exc
                )

            # Sleep in small increments so stop() is responsive.
            self._stop_event.wait(timeout=self._poll_interval)

        logger.debug("NoopQueueDriver._run() exiting")

    def _process_pending_frames(self) -> None:
        """Fetch all pending frames and advance each to completed."""
        try:
            counts = self._store.get_queue_counts()
            pending_count = counts.get("pending", 0)
        except Exception as exc:
            logger.error("NoopQueueDriver: get_queue_counts failed: %s", exc)
            return

        if pending_count == 0:
            return

        # Fetch pending frame IDs directly via a lightweight query.
        pending_frames = self._fetch_pending_frames()
        for frame in pending_frames:
            if self._stop_event.is_set():
                break
            self._advance_frame(frame)

    def _fetch_pending_frames(self) -> list[tuple[int, str]]:
        """Return a list of (frame_id, capture_id) tuples for pending frames.

        Returns an empty list on DB error (driver continues on next poll).
        """
        try:
            import sqlite3 as _sqlite3

            with _sqlite3.connect(str(self._store.db_path)) as conn:
                conn.row_factory = _sqlite3.Row
                rows = conn.execute(
                    "SELECT id, capture_id FROM frames WHERE status = 'pending'"
                ).fetchall()
                return [(row["id"], row["capture_id"]) for row in rows]
        except Exception as exc:
            logger.error("NoopQueueDriver: _fetch_pending_frames failed: %s", exc)
            return []

    def _advance_frame(self, frame: tuple[int, str]) -> None:
        """Advance a single frame: pending → processing → completed.

        Args:
            frame: (frame_id, capture_id) tuple.
        """
        frame_id, capture_id = frame
        request_id = str(uuid.uuid4())

        # --- pending → processing ---
        ok = self._store.advance_frame_status(frame_id, "pending", "processing")
        if not ok:
            # Another thread/process already moved this frame — skip silently.
            logger.debug(
                "NoopQueueDriver: frame_id=%d no longer pending, skipping", frame_id
            )
            return

        # --- processing → completed ---
        ok = self._store.advance_frame_status(frame_id, "processing", "completed")
        if not ok:
            # State machine violation — mark failed.
            logger.warning(
                "NoopQueueDriver: processing→completed failed for frame_id=%d; marking failed",
                frame_id,
            )
            self._mark_failed(frame_id, "STATE_MACHINE_ERROR", request_id, capture_id)
            return

        logger.debug(
            "NoopQueueDriver: frame_id=%d completed capture_id=%s", frame_id, capture_id
        )

    def _mark_failed(
        self,
        frame_id: int,
        reason: str,
        request_id: str,
        capture_id: str,
    ) -> None:
        """Call FramesStore.mark_failed() and emit the Gate log anchor.

        Gate anchor (literal match required by acceptance tests)::

            MRV3 frame_failed reason=<REASON> request_id=<uuid-v4> capture_id=<uuid-v7> frame_id=<int>

        Args:
            frame_id: Primary key (0 if unknown).
            reason: One of DB_WRITE_FAILED | IO_ERROR | STATE_MACHINE_ERROR.
            request_id: UUID v4 of the originating request.
            capture_id: UUID v7 of the capture.
        """
        if reason not in _VALID_REASONS:
            logger.warning(
                "NoopQueueDriver: invalid reason %r; defaulting to STATE_MACHINE_ERROR",
                reason,
            )
            reason = "STATE_MACHINE_ERROR"

        # mark_failed() emits the Gate anchor internally.
        try:
            self._store.mark_failed(
                frame_id=frame_id,
                reason=reason,
                request_id=request_id,
                capture_id=capture_id,
            )
        except Exception as exc:
            # If the DB write itself fails, emit the anchor here so it is
            # never silently lost.
            logger.error(
                "MRV3 frame_failed reason=%s request_id=%s capture_id=%s frame_id=%d",
                "DB_WRITE_FAILED",
                request_id,
                capture_id,
                frame_id,
            )
            logger.error(
                "NoopQueueDriver: mark_failed DB write failed frame_id=%d: %s",
                frame_id,
                exc,
            )
