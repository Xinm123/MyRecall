"""V3ProcessingWorker: OCR-only processing worker for Edge.

This worker implements the OCR processing pipeline:
1. Fetch pending frames from database
2. Validate capture_trigger
3. Execute OCR via RapidOCRBackend
4. Write results to ocr_text table
5. Update frame status and text_source

SSOT: design.md D1-D5, tasks.md §2
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.processing.ocr_processor import OcrStatus, execute_ocr

logger = logging.getLogger(__name__)

# Valid capture_trigger values (P1, lowercase, case-sensitive)
# Per design.md D4: uppercase/mixed-case are INVALID and trigger fail-loud
VALID_CAPTURE_TRIGGERS = frozenset({"idle", "app_switch", "manual", "click"})

# Poll interval for pending frames
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0


class V3ProcessingWorker:
    """Background worker for OCR processing of captured frames.

    Architecture (design.md D1):
    - Daemon thread with start()/stop()/join() interface
    - Poll-loop pattern matching NoopQueueDriver
    - Three-layer idempotency defense (D5)

    Processing flow:
    1. Fetch frames with status='pending'
    2. Validate capture_trigger (fail-loud on invalid)
    3. Execute OCR
    4. On success: write ocr_text, set text_source='ocr', status='completed'
    5. On failure: status='failed', set error_message
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        poll_interval: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._store = FramesStore(db_path=db_path)
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public interface (matches NoopQueueDriver pattern)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background processing thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("V3ProcessingWorker.start() called but thread already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="v3-ocr-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "V3ProcessingWorker started (poll_interval=%.1fs)",
            self._poll_interval,
        )

    def stop(self) -> None:
        """Signal the worker to stop and wait for thread to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 1)
            self._thread = None
        logger.info("V3ProcessingWorker stopped")

    def join(self, timeout: Optional[float] = None) -> None:
        """Block until the worker thread terminates."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal processing loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main poll loop — runs until stop() is called."""
        logger.debug("V3ProcessingWorker._run() entered")
        while not self._stop_event.is_set():
            try:
                self._process_pending_frames()
            except Exception as exc:
                # Broad catch: the loop must never die due to unexpected errors.
                logger.exception(
                    "V3ProcessingWorker: unexpected error in poll loop: %s", exc
                )

            # Sleep in small increments so stop() is responsive.
            self._stop_event.wait(timeout=self._poll_interval)

        logger.debug("V3ProcessingWorker._run() exiting")

    def _process_pending_frames(self) -> None:
        """Fetch and process all pending frames."""
        try:
            pending_frames = self._fetch_pending_frames()
        except Exception as exc:
            logger.error("V3ProcessingWorker: _fetch_pending_frames failed: %s", exc)
            return

        for frame in pending_frames:
            if self._stop_event.is_set():
                break
            self._process_frame(frame)

    def _fetch_pending_frames(self) -> list[tuple]:
        """Fetch pending frames from database.

        Returns list of tuples:
            (frame_id, capture_id, capture_trigger, app_name, window_name, snapshot_path)

        Layer 1 idempotency: only fetch status='pending' frames.
        """
        try:
            with sqlite3.connect(str(self._store.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT id, capture_id, capture_trigger, app_name, window_name, snapshot_path
                    FROM frames
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    """
                ).fetchall()
                return [
                    (
                        row["id"],
                        row["capture_id"],
                        row["capture_trigger"],
                        row["app_name"],
                        row["window_name"],
                        row["snapshot_path"],
                    )
                    for row in rows
                ]
        except sqlite3.Error as exc:
            logger.error("V3ProcessingWorker: _fetch_pending_frames DB error: %s", exc)
            return []

    def _validate_trigger(self, capture_trigger: Optional[str]) -> tuple[bool, str]:
        """Validate capture_trigger value.

        Per design.md D4:
        - Valid values: {'idle', 'app_switch', 'manual', 'click'} (lowercase)
        - NULL or invalid values -> fail-loud
        - Case-sensitive: 'IDLE', 'App_Switch' are INVALID

        Args:
            capture_trigger: The trigger value to validate

        Returns:
            (is_valid, error_message) tuple
        """
        if capture_trigger is None:
            return False, "INVALID_TRIGGER: null"

        if capture_trigger not in VALID_CAPTURE_TRIGGERS:
            return False, f"INVALID_TRIGGER: '{capture_trigger}'"

        return True, ""

    def _process_frame(self, frame: tuple) -> None:
        """Process a single frame: validate -> OCR -> write results.

        Args:
            frame: (frame_id, capture_id, capture_trigger, app_name, window_name, snapshot_path)
        """
        frame_id, capture_id, capture_trigger, app_name, window_name, snapshot_path = frame
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # --- Step 1: pending → processing ---
        ok = self._store.advance_frame_status(frame_id, "pending", "processing")
        if not ok:
            # Another thread/process already moved this frame — skip silently.
            logger.debug(
                "V3ProcessingWorker: frame_id=%d no longer pending, skipping",
                frame_id,
            )
            return

        # --- Step 2: Validate capture_trigger ---
        is_valid, error_reason = self._validate_trigger(capture_trigger)
        if not is_valid:
            # Fail-loud: mark as failed without OCR
            self._mark_failed(
                frame_id=frame_id,
                reason=error_reason,
                request_id=request_id,
                capture_id=capture_id,
            )
            return

        # --- Step 3: Check snapshot_path ---
        if not snapshot_path:
            self._mark_failed(
                frame_id=frame_id,
                reason="OCR_FAILED: missing_snapshot_path",
                request_id=request_id,
                capture_id=capture_id,
            )
            return

        # Verify file exists
        snapshot_file = Path(snapshot_path)
        if not snapshot_file.exists():
            self._mark_failed(
                frame_id=frame_id,
                reason=f"OCR_FAILED: snapshot_not_found path={snapshot_path}",
                request_id=request_id,
                capture_id=capture_id,
            )
            return

        # --- Step 4: Layer 2 idempotency check ---
        if self._store.check_ocr_text_exists(frame_id):
            logger.warning(
                "V3ProcessingWorker: ocr_text already exists for frame_id=%d, skipping",
                frame_id,
            )
            # Advance to completed since OCR was already done
            self._store.advance_frame_status(frame_id, "processing", "completed")
            return

        # --- Step 5: Execute OCR ---
        result = execute_ocr(str(snapshot_file), frame_id=frame_id)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # --- Step 6: Handle OCR result ---
        if result.is_failed or result.status == OcrStatus.EMPTY_TEXT:
            # OCR failed or returned empty text
            error_reason = result.error_reason or "OCR_FAILED: unknown"
            self._mark_failed(
                frame_id=frame_id,
                reason=error_reason,
                request_id=request_id,
                capture_id=capture_id,
            )
            logger.info(
                "MRV3 ocr_failed frame_id=%d reason=%s elapsed_ms=%.1f",
                frame_id,
                error_reason,
                elapsed_ms,
            )
            return

        # --- Step 7: Write ocr_text (Layer 3: INSERT OR IGNORE) ---
        text_json_str = None
        if result.text_json:
            text_json_str = json.dumps(result.text_json)

        inserted = self._store.insert_ocr_text(
            frame_id=frame_id,
            text=result.text,
            text_length=result.text_length,
            ocr_engine="rapidocr",
            app_name=app_name,
            window_name=window_name,
            text_json=text_json_str,
        )
        if not inserted:
            # Row already existed (rare race condition)
            logger.warning(
                "V3ProcessingWorker: ocr_text insert skipped for frame_id=%d (row exists)",
                frame_id,
            )

        # --- Step 8: Update text_source and advance to completed ---
        self._store.update_text_source(frame_id, "ocr")

        # --- Step 9: Write ocr_text to frames table ---
        self._store.update_frames_ocr_text(frame_id, result.text)

        # --- Step 9b: Set full_text for FTS indexing ---
        self._store.update_full_text(frame_id, result.text)

        ok = self._store.advance_frame_status(frame_id, "processing", "completed")
        if not ok:
            logger.error(
                "V3ProcessingWorker: processing→completed failed for frame_id=%d",
                frame_id,
            )
            return

        logger.info(
            "MRV3 ocr_completed frame_id=%d text_length=%d engine=rapidocr elapsed_ms=%.1f",
            frame_id,
            result.text_length,
            elapsed_ms,
        )

    def _mark_failed(
        self,
        frame_id: int,
        reason: str,
        request_id: str,
        capture_id: str,
    ) -> None:
        """Mark frame as failed with error reason.

        Args:
            frame_id: The frame ID
            reason: Error reason string
            request_id: Request ID for tracking
            capture_id: Capture ID for logging
        """
        # Emit Gate log anchor
        logger.error(
            "MRV3 frame_failed reason=%s request_id=%s capture_id=%s frame_id=%d",
            reason,
            request_id,
            capture_id,
            frame_id,
        )

        try:
            self._store.mark_failed(
                frame_id=frame_id,
                reason=reason,
                request_id=request_id,
                capture_id=capture_id,
            )
        except Exception as exc:
            logger.error(
                "V3ProcessingWorker: mark_failed DB write failed frame_id=%d: %s",
                frame_id,
                exc,
            )
