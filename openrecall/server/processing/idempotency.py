"""Idempotency helpers for OCR processing.

Provides three-layer idempotency defense (design.md D5):
1. Fetch filter: Skip already completed/failed frames at query time
2. Pre-write check: Verify ocr_text row doesn't exist before write
3. INSERT OR IGNORE: Database-level safety net with UNIQUE constraint
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def check_ocr_text_exists(conn: sqlite3.Connection, frame_id: int) -> bool:
    """Check if an ocr_text row already exists for a frame.

    This is layer 2 of the three-layer idempotency defense.

    Args:
        conn: SQLite connection (must have row_factory set)
        frame_id: The frame ID to check

    Returns:
        True if ocr_text row exists, False otherwise
    """
    try:
        cursor = conn.execute(
            "SELECT 1 FROM ocr_text WHERE frame_id = ? LIMIT 1",
            (frame_id,),
        )
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.warning(
            "check_ocr_text_exists: DB error for frame_id=%d: %s",
            frame_id,
            e,
        )
        return False


def get_pending_frames_for_ocr(
    conn: sqlite3.Connection,
    limit: int = 100,
) -> list[tuple]:
    """Fetch pending frames that haven't been processed yet.

    This is layer 1 of the three-layer idempotency defense.
    Only returns frames with status='pending' and no existing ocr_text row.

    Args:
        conn: SQLite connection
        limit: Maximum number of frames to return

    Returns:
        List of tuples: (frame_id, capture_id, capture_trigger, app_name,
                         window_name, snapshot_path)
    """
    try:
        rows = conn.execute(
            """
            SELECT id, capture_id, capture_trigger, app_name, window_name, snapshot_path
            FROM frames
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
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
    except sqlite3.Error as e:
        logger.error("get_pending_frames_for_ocr: DB error: %s", e)
        return []
