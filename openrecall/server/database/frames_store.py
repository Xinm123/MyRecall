"""v3 FramesStore: SQLite-backed store for the `frames` table."""

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _to_utc_iso8601(value: object) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    if isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        try:
            numeric_raw = float(raw)
            dt = datetime.fromtimestamp(numeric_raw, tz=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            pass

        normalized = raw.replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        elif "+" not in normalized and "-" not in normalized[10:]:
            normalized = f"{normalized}+00:00"

        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    return None


def normalize_timestamp_filter(value: object) -> Optional[str]:
    return _to_utc_iso8601(value)


def _parse_utc_datetime(value: object) -> Optional[datetime]:
    normalized = _to_utc_iso8601(value)
    if normalized is None:
        return None
    return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _percentile(values: list[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])

    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


@dataclass
class Frame:
    id: int
    capture_id: str
    timestamp: str
    app_name: Optional[str]
    window_name: Optional[str]
    snapshot_path: Optional[str]
    status: str
    ingested_at: str
    image_size_bytes: Optional[int]
    error_message: Optional[str]
    last_known_app: Optional[str] = None
    last_known_window: Optional[str] = None


class FramesStore:
    """Read/write access to the v3 `frames` table in edge.db.

    All count queries hit the DB directly — no in-process counters.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or settings.db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _row_to_frame(self, row: sqlite3.Row) -> Frame:
        columns = row.keys() if hasattr(row, "keys") else []
        return Frame(
            id=row["id"],
            capture_id=row["capture_id"],
            timestamp=row["timestamp"],
            app_name=row["app_name"],
            window_name=row["window_name"],
            snapshot_path=row["snapshot_path"],
            status=row["status"],
            ingested_at=row["ingested_at"],
            image_size_bytes=row["image_size_bytes"],
            error_message=row["error_message"],
            last_known_app=row["last_known_app"]
            if "last_known_app" in columns
            else None,
            last_known_window=row["last_known_window"]
            if "last_known_window" in columns
            else None,
        )

    def _extract_metadata_fields(
        self, metadata: dict[str, object]
    ) -> tuple[object, ...]:
        raw_timestamp = metadata.get("timestamp") or metadata.get("capture_time")
        timestamp = _to_utc_iso8601(raw_timestamp) or ""
        app_name = (
            metadata.get("app_name")
            or metadata.get("app")
            or metadata.get("active_app")
        )
        window_name = (
            metadata.get("window_name")
            or metadata.get("window")
            or metadata.get("active_window")
        )
        browser_url = metadata.get("browser_url")
        focused = metadata.get("focused")
        device_name = metadata.get("device_name") or "monitor_0"
        capture_trigger = metadata.get("capture_trigger")
        event_ts = _to_utc_iso8601(metadata.get("event_ts"))
        image_size_bytes = metadata.get("image_size_bytes")
        last_known_app = metadata.get("last_known_app")
        last_known_window = metadata.get("last_known_window")
        simhash = metadata.get("simhash")
        phash = metadata.get("phash")
        return (
            timestamp,
            app_name,
            window_name,
            browser_url,
            focused,
            device_name,
            capture_trigger,
            event_ts,
            image_size_bytes,
            last_known_app,
            last_known_window,
            simhash,
            phash,
        )

    def claim_frame(
        self, capture_id: str, metadata: dict[str, object]
    ) -> tuple[int, bool]:
        (
            timestamp,
            app_name,
            window_name,
            browser_url,
            focused,
            device_name,
            capture_trigger,
            event_ts,
            image_size_bytes,
            last_known_app,
            last_known_window,
            simhash,
            phash,
        ) = self._extract_metadata_fields(metadata)
        # Convert unsigned 64-bit hash values to signed for SQLite compatibility.
        # SQLite INTEGER is signed 64-bit. Both simhash and phash produce unsigned 64-bit values.
        # We store as signed using two's complement representation (same bits).
        # This aligns with screenpipe's i64 storage approach.
        if simhash is not None and isinstance(simhash, int):
            # Convert values > 2^63-1 to their signed equivalents
            if simhash > 9223372036854775807:  # 2^63 - 1
                simhash = simhash - 18446744073709551616  # 2^64
        if phash is not None and isinstance(phash, int):
            if phash > 9223372036854775807:  # 2^63 - 1
                phash = phash - 18446744073709551616  # 2^64

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO frames
                        (capture_id, timestamp, app_name, window_name, browser_url,
                         focused, device_name, capture_trigger, event_ts, snapshot_path,
                         image_size_bytes, status, last_known_app, last_known_window, simhash, phash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                    """,
                    (
                        capture_id,
                        timestamp,
                        app_name,
                        window_name,
                        browser_url,
                        focused,
                        device_name,
                        capture_trigger,
                        event_ts,
                        None,
                        image_size_bytes,
                        last_known_app,
                        last_known_window,
                        simhash,
                        phash,
                    ),
                )
                conn.commit()
                is_new = cursor.rowcount > 0

                if is_new:
                    last_row_id = cursor.lastrowid
                    if last_row_id is None:
                        raise sqlite3.IntegrityError(
                            f"claim_frame inserted but no lastrowid capture_id={capture_id}"
                        )
                    frame_id = last_row_id
                    logger.info(
                        "claim_frame: winner capture_id=%s frame_id=%d",
                        capture_id,
                        frame_id,
                    )
                    return frame_id, True

                row = conn.execute(
                    "SELECT id FROM frames WHERE capture_id = ?",
                    (capture_id,),
                ).fetchone()
                if row is None:
                    # In high concurrency, this row could theoretically have been deleted
                    # between INSERT OR IGNORE and this SELECT, though extremely unlikely.
                    raise sqlite3.IntegrityError(
                        f"INSERT OR IGNORE rowcount=0 but row not found capture_id={capture_id}"
                    )
                existing_id: int = row["id"]
                logger.debug(
                    "claim_frame: duplicate capture_id=%s frame_id=%d",
                    capture_id,
                    existing_id,
                )
                return existing_id, False

        except sqlite3.Error as e:
            logger.error("claim_frame failed capture_id=%s: %s", capture_id, e)
            raise

    def finalize_claimed_frame(
        self,
        frame_id: int,
        capture_id: str,
        snapshot_path: str,
    ) -> bool:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE frames
                    SET snapshot_path = ?
                    WHERE id = ? AND capture_id = ? AND snapshot_path IS NULL
                    """,
                    (snapshot_path, frame_id, capture_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(
                "finalize_claimed_frame failed capture_id=%s frame_id=%d: %s",
                capture_id,
                frame_id,
                e,
            )
            raise

    def delete_unfinalized_claim(self, frame_id: int, capture_id: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    DELETE FROM frames
                    WHERE id = ? AND capture_id = ? AND snapshot_path IS NULL
                    """,
                    (frame_id, capture_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.warning(
                "delete_unfinalized_claim failed capture_id=%s frame_id=%d: %s",
                capture_id,
                frame_id,
                e,
            )

    def get_frame(self, frame_id: int) -> Optional[Frame]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, capture_id, timestamp, app_name, window_name,
                           snapshot_path, status, ingested_at, image_size_bytes, error_message,
                           last_known_app, last_known_window
                    FROM frames WHERE id = ?
                    """,
                    (frame_id,),
                ).fetchone()
                return self._row_to_frame(row) if row else None
        except sqlite3.Error as e:
            logger.error("get_frame failed frame_id=%d: %s", frame_id, e)
            return None

    def get_frame_by_capture_id(self, capture_id: str) -> Optional[Frame]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, capture_id, timestamp, app_name, window_name,
                           snapshot_path, status, ingested_at, image_size_bytes, error_message,
                           last_known_app, last_known_window
                    FROM frames WHERE capture_id = ?
                    """,
                    (capture_id,),
                ).fetchone()
                return self._row_to_frame(row) if row else None
        except sqlite3.Error as e:
            logger.error(
                "get_frame_by_capture_id failed capture_id=%s: %s", capture_id, e
            )
            return None

    def get_queue_counts(self) -> dict[str, int]:
        counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT status, COUNT(*) AS cnt FROM frames GROUP BY status"
                ).fetchall()
                for row in rows:
                    if row["status"] in counts:
                        counts[row["status"]] = row["cnt"]
        except sqlite3.Error as e:
            logger.error("get_queue_counts failed: %s", e)
        return counts

    def get_oldest_pending_ingested_at(self) -> Optional[str]:
        """Returns None when no pending frames exist — never empty string or current time."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT MIN(ingested_at) AS oldest FROM frames WHERE status = 'pending'"
                ).fetchone()
                if row is None:
                    return None
                value = row["oldest"]
                # SQLite MIN() returns SQL NULL when no rows match, which becomes None here
                return value if value else None
        except sqlite3.Error as e:
            logger.error("get_oldest_pending_ingested_at failed: %s", e)
            return None

    def get_pending_count(self) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM frames WHERE status = 'pending'"
                ).fetchone()
                return row["cnt"] if row else 0
        except sqlite3.Error as e:
            logger.error("get_pending_count failed: %s", e)
            return 0

    def advance_frame_status(
        self,
        frame_id: int,
        from_status: str,
        to_status: str,
    ) -> bool:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE frames
                    SET status = ?,
                        processed_at = CASE
                            WHEN ? = 'completed'
                            THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                            ELSE processed_at
                        END
                    WHERE id = ? AND status = ?
                    """,
                    (to_status, to_status, frame_id, from_status),
                )
                conn.commit()
                updated = cursor.rowcount > 0
                if not updated:
                    logger.warning(
                        "advance_frame_status: no row updated frame_id=%d %s->%s",
                        frame_id,
                        from_status,
                        to_status,
                    )
                return updated
        except sqlite3.Error as e:
            logger.error(
                "advance_frame_status failed frame_id=%d %s->%s: %s",
                frame_id,
                from_status,
                to_status,
                e,
            )
            return False

    def mark_failed(
        self,
        frame_id: int,
        reason: str,
        request_id: str,
        capture_id: str,
    ) -> bool:
        """Mark frame as failed and emit the Gate log anchor.

        Gate anchor (literal match required):
            MRV3 frame_failed reason=<REASON> request_id=<uuid-v4> capture_id=<uuid-v7> frame_id=<int>

        Args:
            frame_id: Primary key (pass 0 if unknown at failure point).
            reason: One of DB_WRITE_FAILED | IO_ERROR | STATE_MACHINE_ERROR.
            request_id: UUID v4 of the originating request.
            capture_id: UUID v7 of the capture.
        """
        if not request_id:
            request_id = str(uuid.uuid4())

        logger.error(
            "MRV3 frame_failed reason=%s request_id=%s capture_id=%s frame_id=%d",
            reason,
            request_id,
            capture_id,
            frame_id,
        )

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE frames SET status = 'failed', error_message = ? WHERE id = ?",
                    (reason, frame_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(
                "mark_failed DB update failed frame_id=%d reason=%s: %s",
                frame_id,
                reason,
                e,
            )
            return False

    def get_last_frame_timestamp(self) -> Optional[str]:
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT MAX(timestamp) AS ts FROM frames").fetchone()
                if row is None:
                    return None
                return _to_utc_iso8601(row["ts"])
        except sqlite3.Error as e:
            logger.error("get_last_frame_timestamp failed: %s", e)
            return None

    def get_last_frame_ingested_at(self) -> Optional[str]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT MAX(ingested_at) AS ts FROM frames"
                ).fetchone()
                return row["ts"] if row and row["ts"] else None
        except sqlite3.Error as e:
            logger.error("get_last_frame_ingested_at failed: %s", e)
            return None

    def get_recent_memories(self, limit: int = 500) -> list[dict[str, object]]:
        """Retrieve recent frames for the grid view.

        Args:
            limit: Maximum number of frames to return.

        Returns:
            List of dicts with frame data formatted for UI consumption.
            Includes OCR-related fields via LEFT JOIN (P1-S3).
        """
        memories = []
        normalized_limit = max(1, min(int(limit) if limit else 500, 1000))

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT f.id, f.capture_id, f.timestamp, f.app_name, f.window_name,
                           f.snapshot_path, f.status, f.ingested_at, f.last_known_app,
                           f.last_known_window, f.text_source, f.processed_at,
                           f.capture_trigger, f.device_name, f.error_message,
                           o.text_length, o.ocr_engine, o.text AS ocr_text,
                           SUBSTR(o.text, 1, 100) AS ocr_text_preview
                    FROM frames f
                    LEFT JOIN ocr_text o ON f.id = o.frame_id
                    ORDER BY f.timestamp DESC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]
                    memories.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.png",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                            # P1-S3 additions
                            "text_source": row["text_source"] or "",
                            "text_length": row["text_length"] or 0,
                            "ocr_text": row["ocr_text"] or "",
                            "ocr_text_preview": row["ocr_text_preview"] or "",
                            "ocr_engine": row["ocr_engine"] or "",
                            "processed_at": row["processed_at"] or "",
                            "capture_trigger": row["capture_trigger"] or "",
                            "device_name": row["device_name"] or "",
                            "error_message": row["error_message"] or "",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_recent_memories failed: %s", e)
        return memories

    def get_timeline_frames(self, limit: int = 5000) -> list[dict[str, object]]:
        """Retrieve frames for timeline view.

        Args:
            limit: Maximum number of frames to return.

        Returns:
            List of dicts with frame data formatted for timeline view.
        """
        frames = []
        normalized_limit = max(1, min(int(limit) if limit else 5000, 10000))

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, capture_id, timestamp, app_name, window_name,
                           snapshot_path, status, ingested_at, last_known_app, last_known_window
                    FROM frames
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]
                    frames.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.png",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_timeline_frames failed: %s", e)
        return frames

    def get_memories_since(self, timestamp: str) -> list[dict[str, object]]:
        """Retrieve frames with timestamp greater than given value.

        Args:
            timestamp: Filter for frames with timestamp > this value (ISO8601 string or Unix timestamp string).

        Returns:
            List of dicts with frame data.
            Includes OCR-related fields via LEFT JOIN (P1-S3).
        """
        memories = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT f.id, f.capture_id, f.timestamp, f.app_name, f.window_name,
                           f.snapshot_path, f.status, f.ingested_at, f.last_known_app,
                           f.last_known_window, f.text_source, f.processed_at,
                           f.capture_trigger, f.device_name, f.error_message,
                           o.text_length, o.ocr_engine, o.text AS ocr_text,
                           SUBSTR(o.text, 1, 100) AS ocr_text_preview
                    FROM frames f
                    LEFT JOIN ocr_text o ON f.id = o.frame_id
                    WHERE f.timestamp > ?
                    ORDER BY f.timestamp DESC
                    """,
                    (timestamp,),
                ).fetchall()

                for row in rows:
                    ts = row["timestamp"]
                    memories.append(
                        {
                            "id": row["id"],
                            "frame_id": row["id"],
                            "capture_id": row["capture_id"],
                            "timestamp": ts,
                            "app": row["app_name"] or "",
                            "title": row["window_name"] or "",
                            "status": (row["status"] or "pending").upper(),
                            "filename": f"{ts}.png",
                            "app_name": row["app_name"] or "",
                            "window_title": row["window_name"] or "",
                            "last_known_app": row["last_known_app"] or "",
                            "last_known_window": row["last_known_window"] or "",
                            # P1-S3 additions
                            "text_source": row["text_source"] or "",
                            "text_length": row["text_length"] or 0,
                            "ocr_text": row["ocr_text"] or "",
                            "ocr_text_preview": row["ocr_text_preview"] or "",
                            "ocr_engine": row["ocr_engine"] or "",
                            "processed_at": row["processed_at"] or "",
                            "capture_trigger": row["capture_trigger"] or "",
                            "device_name": row["device_name"] or "",
                            "error_message": row["error_message"] or "",
                        }
                    )
        except sqlite3.Error as e:
            logger.error("get_memories_since failed: %s", e)
        return memories

    def get_capture_latency_summary(
        self, window_seconds: int = 300
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window_seconds)
        window_start_iso = window_start.isoformat().replace("+00:00", "Z")
        values: list[float] = []
        anomaly_count = 0

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT event_ts, ingested_at
                    FROM frames
                    WHERE ingested_at >= ?
                    ORDER BY ingested_at ASC
                    """,
                    (window_start_iso,),
                ).fetchall()
        except sqlite3.Error as e:
            logger.error("get_capture_latency_summary failed: %s", e)
            rows = []

        for row in rows:
            ingested_at = _parse_utc_datetime(row["ingested_at"])
            event_ts = _parse_utc_datetime(row["event_ts"])
            if ingested_at is None or event_ts is None:
                anomaly_count += 1
                continue
            latency_ms = (ingested_at - event_ts).total_seconds() * 1000.0
            if latency_ms < 0:
                anomaly_count += 1
                continue
            values.append(latency_ms)

        return {
            "capture_latency_p50": _percentile(values, 0.50),
            "capture_latency_p90": _percentile(values, 0.90),
            "capture_latency_p95": _percentile(values, 0.95),
            "capture_latency_p99": _percentile(values, 0.99),
            "capture_latency_sample_count": len(values),
            "capture_latency_anomaly_count": anomaly_count,
            "window_id": f"{int(window_start.timestamp())}-{int(now.timestamp())}",
            "edge_pid": os.getpid(),
            "broken_window": False,
        }

    def get_status_sync_summary(self, window_seconds: int = 300) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=window_seconds)
        window_start_iso = window_start.isoformat().replace("+00:00", "Z")
        values: list[float] = []

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT ingested_at, processed_at
                    FROM frames
                    WHERE status = 'completed'
                      AND processed_at IS NOT NULL
                      AND processed_at >= ?
                    ORDER BY processed_at ASC
                    """,
                    (window_start_iso,),
                ).fetchall()
        except sqlite3.Error as e:
            logger.error("get_status_sync_summary failed: %s", e)
            rows = []

        for row in rows:
            ingested_at = _parse_utc_datetime(row["ingested_at"])
            processed_at = _parse_utc_datetime(row["processed_at"])
            if ingested_at is None or processed_at is None:
                continue
            latency_ms = (processed_at - ingested_at).total_seconds() * 1000.0
            if latency_ms < 0:
                continue
            values.append(latency_ms)

        return {
            "status_sync_p50": _percentile(values, 0.50),
            "status_sync_p90": _percentile(values, 0.90),
            "status_sync_p95": _percentile(values, 0.95),
            "status_sync_p99": _percentile(values, 0.99),
            "status_sync_sample_count": len(values),
            "window_id": f"{int(window_start.timestamp())}-{int(now.timestamp())}",
            "edge_pid": os.getpid(),
            "broken_window": False,
        }

    # ------------------------------------------------------------------
    # OCR Text Methods (P1-S3)
    # ------------------------------------------------------------------

    def insert_ocr_text(
        self,
        frame_id: int,
        text: str,
        text_length: int,
        ocr_engine: str,
        app_name: Optional[str],
        window_name: Optional[str],
        text_json: Optional[str] = None,
    ) -> bool:
        """Insert OCR text result for a frame.

        Uses INSERT OR IGNORE for idempotency (layer 3 of D5 defense).
        Front-guard assertion prevents accidental empty-text writes.

        Args:
            frame_id: The frame ID
            text: Extracted OCR text (must be non-empty)
            text_length: Length of the text
            ocr_engine: Engine name (e.g., 'rapidocr')
            app_name: Application name from frame metadata
            window_name: Window name from frame metadata
            text_json: JSON string with bounding boxes for future UI features

        Returns:
            True if inserted, False if row already existed or error
        """
        # Front-guard: prevent empty text writes
        assert text and len(text) > 0, (
            f"insert_ocr_text: refusing empty text for frame_id={frame_id}"
        )

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO ocr_text
                        (frame_id, text, text_length, text_json, ocr_engine, app_name, window_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (frame_id, text, text_length, text_json, ocr_engine, app_name, window_name),
                )
                conn.commit()
                inserted = cursor.rowcount > 0
                if not inserted:
                    logger.warning(
                        "insert_ocr_text: row already exists for frame_id=%d",
                        frame_id,
                    )
                return inserted
        except sqlite3.Error as e:
            logger.error("insert_ocr_text failed frame_id=%d: %s", frame_id, e)
            return False

    def update_text_source(self, frame_id: int, text_source: str) -> bool:
        """Update the text_source field for a frame.

        Args:
            frame_id: The frame ID
            text_source: Source identifier (e.g., 'ocr')

        Returns:
            True if updated, False otherwise
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE frames SET text_source = ? WHERE id = ?",
                    (text_source, frame_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(
                "update_text_source failed frame_id=%d: %s", frame_id, e
            )
            return False

    def check_ocr_text_exists(self, frame_id: int) -> bool:
        """Check if an ocr_text row exists for a frame.

        Args:
            frame_id: The frame ID to check

        Returns:
            True if ocr_text row exists, False otherwise
        """
        try:
            with self._connect() as conn:
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

    # ------------------------------------------------------------------
    # Accessibility Canonical Methods (Phase 5)
    # ------------------------------------------------------------------

    def complete_accessibility_frame(
        self,
        frame_id: int,
        text: str,
        browser_url: Optional[str],
        content_hash: Optional[int],
        simhash: Optional[int],
        accessibility_tree_json: str,
        accessibility_text_content: str,
        accessibility_node_count: int,
        accessibility_truncated: bool,
        elements: list[dict],
    ) -> bool:
        """Complete a frame with accessibility-canonical data in one transaction.

        Writes to:
        - frames (text, text_source, accessibility_tree_json, browser_url,
                  content_hash, simhash, status, processed_at)
        - accessibility table
        - elements table with derived parent_id and sort_order

        Args:
            frame_id: The frame ID to complete
            text: The extracted text content
            browser_url: Optional browser URL
            content_hash: Optional content hash for deduplication
            simhash: Optional similarity hash
            accessibility_tree_json: JSON string of the accessibility tree
            accessibility_text_content: Text content from accessibility
            accessibility_node_count: Number of nodes in the tree
            accessibility_truncated: Whether the tree was truncated
            elements: List of element dicts with role, text, depth, bounds

        Returns:
            True if completed successfully, False otherwise
        """
        # Convert unsigned 64-bit integers to signed for SQLite compatibility.
        # SQLite INTEGER is signed 64-bit. content_hash/simhash may be unsigned 64-bit.
        if content_hash is not None and isinstance(content_hash, int):
            if content_hash > 9223372036854775807:  # 2^63 - 1
                content_hash = content_hash - 18446744073709551616  # 2^64
        if simhash is not None and isinstance(simhash, int):
            if simhash > 9223372036854775807:  # 2^63 - 1
                simhash = simhash - 18446744073709551616  # 2^64

        try:
            with self._connect() as conn:
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                # Update frames table
                conn.execute(
                    """
                    UPDATE frames SET
                        text = ?,
                        text_source = 'accessibility',
                        accessibility_tree_json = ?,
                        browser_url = COALESCE(?, browser_url),
                        content_hash = ?,
                        simhash = ?,
                        status = 'completed',
                        processed_at = ?
                    WHERE id = ?
                    """,
                    (
                        text,
                        accessibility_tree_json,
                        browser_url,
                        content_hash,
                        simhash,
                        now,
                        frame_id,
                    ),
                )

                # Get frame metadata for accessibility row
                frame_row = conn.execute(
                    "SELECT timestamp, app_name, window_name FROM frames WHERE id = ?",
                    (frame_id,),
                ).fetchone()

                if frame_row is None:
                    logger.error(
                        "complete_accessibility_frame: frame not found id=%d",
                        frame_id,
                    )
                    return False

                # Delete existing accessibility row if any (idempotency)
                conn.execute(
                    "DELETE FROM accessibility WHERE frame_id = ?",
                    (frame_id,),
                )

                # Insert accessibility row
                conn.execute(
                    """
                    INSERT INTO accessibility (
                        frame_id, timestamp, app_name, window_name, browser_url,
                        text_content, text_length
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        frame_id,
                        frame_row["timestamp"],
                        frame_row["app_name"] or "",
                        frame_row["window_name"] or "",
                        browser_url,
                        accessibility_text_content,
                        len(accessibility_text_content),
                    ),
                )

                # Delete existing elements if any (idempotency)
                conn.execute(
                    "DELETE FROM elements WHERE frame_id = ?",
                    (frame_id,),
                )

                # Insert elements with parent_id and sort_order derivation
                self._insert_elements_with_parent_derivation(conn, frame_id, elements)

                conn.commit()
                return True

        except sqlite3.Error as e:
            logger.error(
                "complete_accessibility_frame failed frame_id=%d: %s",
                frame_id,
                e,
            )
            return False

    def _insert_elements_with_parent_derivation(
        self, conn: sqlite3.Connection, frame_id: int, elements: list[dict]
    ) -> None:
        """Insert elements with parent_id and sort_order derived from depth-first ordering.

        The depth stack tracks the path from root to current position, enabling
        correct parent_id assignment as we traverse the tree in depth-first order.

        Args:
            conn: Active database connection
            frame_id: The frame ID
            elements: List of element dicts in depth-first order
        """
        depth_stack: list[tuple[int, int]] = []  # Stack of (depth, element_id)

        for sort_order, elem in enumerate(elements):
            depth = elem.get("depth", 0)

            # Pop stack until we find a shallower depth (potential parent)
            while depth_stack and depth_stack[-1][0] >= depth:
                depth_stack.pop()

            # Parent is the last element with depth < current depth
            parent_id = depth_stack[-1][1] if depth_stack else None

            # Extract bounds if present
            bounds = elem.get("bounds") or {}
            left_bound = bounds.get("left") if isinstance(bounds, dict) else None
            top_bound = bounds.get("top") if isinstance(bounds, dict) else None
            width_bound = bounds.get("width") if isinstance(bounds, dict) else None
            height_bound = bounds.get("height") if isinstance(bounds, dict) else None

            # Insert element
            cursor = conn.execute(
                """
                INSERT INTO elements (
                    frame_id, source, role, text, parent_id, depth,
                    left_bound, top_bound, width_bound, height_bound, sort_order
                ) VALUES (?, 'accessibility', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    frame_id,
                    elem.get("role"),
                    elem.get("text"),
                    parent_id,
                    depth,
                    left_bound,
                    top_bound,
                    width_bound,
                    height_bound,
                    sort_order,
                ),
            )

            # Push current element to stack
            depth_stack.append((depth, cursor.lastrowid))

    def list_accessibility_for_frame(self, frame_id: int) -> list[dict]:
        """Get accessibility rows for a frame.

        Args:
            frame_id: The frame ID

        Returns:
            List of accessibility row dicts
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM accessibility WHERE frame_id = ?",
                    (frame_id,),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error(
                "list_accessibility_for_frame failed frame_id=%d: %s",
                frame_id,
                e,
            )
            return []

    def list_elements_for_frame(self, frame_id: int) -> list[dict]:
        """Get elements rows for a frame.

        Args:
            frame_id: The frame ID

        Returns:
            List of element row dicts in sort_order
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM elements WHERE frame_id = ? ORDER BY sort_order",
                    (frame_id,),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error(
                "list_elements_for_frame failed frame_id=%d: %s",
                frame_id,
                e,
            )
            return []

    def get_frame_by_id(self, frame_id: int) -> Optional[dict]:
        """Get a frame by ID as a dict with all fields.

        Args:
            frame_id: The frame ID

        Returns:
            Frame dict or None if not found
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM frames WHERE id = ?",
                    (frame_id,),
                ).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("get_frame_by_id failed frame_id=%d: %s", frame_id, e)
            return None

    # ------------------------------------------------------------------
    # Chat MVP Query Helpers (Phase 6)
    # ------------------------------------------------------------------

    # Text-like roles for recent_texts query.
    # Note: In MVP, only AXStaticText exists in accessibility elements.
    # 'line' and 'paragraph' are OCR hierarchy roles (source='ocr') that don't exist
    # in MVP accessibility data. They are kept for screenpipe query compatibility
    # and future OCR elements support.
    # MVP: Only AXStaticText exists in accessibility elements.
    # 'line' and 'paragraph' are OCR hierarchy roles that don't exist
    # when source='accessibility'. Kept minimal for clarity.
    TEXT_LIKE_ROLES = ("AXStaticText",)

    def get_activity_summary_apps(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> list[dict]:
        """Return apps with frame counts and approximate minutes.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp
            app_name: Optional filter by app name

        Returns:
            List of dicts with name, frame_count, minutes (approximate)
        """
        apps = []
        try:
            with self._connect() as conn:
                sql = """
                    SELECT app_name AS name, COUNT(*) AS frame_count
                    FROM frames
                    WHERE status = 'completed'
                      AND timestamp >= ?
                      AND timestamp <= ?
                """
                params: list = [start_time, end_time]

                if app_name:
                    sql += " AND app_name = ?"
                    params.append(app_name)

                sql += " GROUP BY app_name ORDER BY frame_count DESC"

                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    # minutes = frame_count * 2 / 60 (approximate)
                    frame_count = row["frame_count"]
                    minutes = frame_count * 2.0 / 60.0
                    apps.append({
                        "name": row["name"] or "Unknown",
                        "frame_count": frame_count,
                        "minutes": round(minutes, 2),
                    })
        except sqlite3.Error as e:
            logger.error("get_activity_summary_apps failed: %s", e)
        return apps

    def get_activity_summary_recent_texts(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """Return recent text-like elements from accessibility.

        Only AXStaticText is matched in MVP because 'line' and 'paragraph'
        are OCR hierarchy roles that don't exist in accessibility elements.

        Uses ROW_NUMBER() OVER (PARTITION BY text) to dedupe identical text
        while preserving frame_id and role from the most recent occurrence.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp
            app_name: Optional filter by app name
            limit: Maximum number of results (default 10)

        Returns:
            List of dicts with frame_id, text, app_name, timestamp, role
        """
        texts = []
        try:
            with self._connect() as conn:
                # Use window function to dedupe by text while keeping
                # frame_id and role from the most recent occurrence
                sql = """
                    SELECT frame_id, text, role, app_name, timestamp
                    FROM (
                        SELECT
                            e.frame_id,
                            e.text,
                            e.role,
                            f.app_name,
                            f.timestamp,
                            ROW_NUMBER() OVER (PARTITION BY e.text ORDER BY f.timestamp DESC) as rn
                        FROM elements e
                        JOIN frames f ON e.frame_id = f.id
                        WHERE e.source = 'accessibility'
                          AND e.role = ?
                          AND f.status = 'completed'
                          AND f.timestamp >= ?
                          AND f.timestamp <= ?
                """
                params: list = [
                    self.TEXT_LIKE_ROLES[0],
                    start_time,
                    end_time,
                ]

                if app_name:
                    sql += " AND f.app_name = ?"
                    params.append(app_name)

                sql += """
                    )
                    WHERE rn = 1
                    ORDER BY timestamp DESC LIMIT ?
                """
                params.append(limit)

                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    texts.append({
                        "frame_id": row["frame_id"],
                        "text": row["text"] or "",
                        "role": row["role"],
                        "app_name": row["app_name"] or "",
                        "timestamp": row["timestamp"],
                    })
        except sqlite3.Error as e:
            logger.error("get_activity_summary_recent_texts failed: %s", e)
        return texts

    def get_activity_summary_total_frames(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> int:
        """Return count of completed frames in time range.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp
            app_name: Optional filter by app name

        Returns:
            Count of completed frames
        """
        try:
            with self._connect() as conn:
                sql = """
                    SELECT COUNT(*) AS cnt
                    FROM frames
                    WHERE status = 'completed'
                      AND timestamp >= ?
                      AND timestamp <= ?
                """
                params: list = [start_time, end_time]

                if app_name:
                    sql += " AND app_name = ?"
                    params.append(app_name)

                row = conn.execute(sql, params).fetchone()
                return row["cnt"] if row else 0
        except sqlite3.Error as e:
            logger.error("get_activity_summary_total_frames failed: %s", e)
            return 0

    def get_activity_summary_time_range(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Return min/max timestamps of completed frames in time range.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp
            app_name: Optional filter by app name

        Returns:
            Dict with start/end timestamps or None if no frames
        """
        try:
            with self._connect() as conn:
                sql = """
                    SELECT MIN(timestamp) AS start, MAX(timestamp) AS end
                    FROM frames
                    WHERE status = 'completed'
                      AND timestamp >= ?
                      AND timestamp <= ?
                """
                params: list = [start_time, end_time]

                if app_name:
                    sql += " AND app_name = ?"
                    params.append(app_name)

                row = conn.execute(sql, params).fetchone()
                if row and row["start"] and row["end"]:
                    return {
                        "start": row["start"],
                        "end": row["end"],
                    }
                return None
        except sqlite3.Error as e:
            logger.error("get_activity_summary_time_range failed: %s", e)
            return None

    def get_frame_context(
        self,
        frame_id: int,
        max_text_length: Optional[int] = None,
        max_nodes: Optional[int] = None,
    ) -> Optional[dict]:
        """Return frame context for chat grounding.

        Returns frame data including:
        - frame_id, text, text_source
        - nodes: parsed from accessibility_tree_json (text nodes only, aligns with screenpipe)
        - urls: extracted from link-like nodes and text

        Truncation (aligns with screenpipe MCP layer):
        - By default, returns complete data (no truncation)
        - When max_text_length is set, truncates text with "..." suffix
        - When max_nodes is set, limits nodes and adds nodes_truncated count

        Args:
            frame_id: The frame ID
            max_text_length: Optional max text length (default: None = no limit)
            max_nodes: Optional max nodes count (default: None = no limit)

        Returns:
            Dict with frame context or None if not found
        """
        try:
            with self._connect() as conn:
                # Join with ocr_text table for OCR frames
                # frames.text is used for accessibility frames, ocr_text.text for OCR frames
                row = conn.execute(
                    """
                    SELECT f.id, f.text, f.text_source, f.accessibility_tree_json,
                           f.browser_url, f.status, o.text AS ocr_text
                    FROM frames f
                    LEFT JOIN ocr_text o ON f.id = o.frame_id
                    WHERE f.id = ?
                    """,
                    (frame_id,),
                ).fetchone()

                if row is None:
                    return None

                frame_id_val = row["id"]
                # Use ocr_text for OCR frames, frames.text for accessibility frames
                if row["text_source"] == "ocr" and row["ocr_text"]:
                    text = row["ocr_text"]
                else:
                    text = row["text"] or ""
                text_source = row["text_source"]
                tree_json = row["accessibility_tree_json"]
                browser_url = row["browser_url"]
                status = row["status"]

                raw_nodes: list[dict] = []
                urls: list[str] = []
                nodes_truncated: Optional[int] = None

                # Parse accessibility tree if available
                if tree_json:
                    try:
                        raw_nodes = json.loads(tree_json)
                    except (json.JSONDecodeError, TypeError):
                        raw_nodes = []

                # Filter nodes: only include nodes with non-empty text (aligns with screenpipe)
                # screenpipe: `if !text.is_empty() { nodes.push(...) }`
                nodes = []
                for node in raw_nodes:
                    node_text = node.get("text", "")
                    if node_text:  # Skip empty-text nodes
                        nodes.append(node)

                # Extract URLs from link-like nodes (aligns with screenpipe)
                # screenpipe: `role_lower.contains("link") || role_lower.contains("hyperlink")`
                for node in nodes:
                    role = (node.get("role") or "").lower()
                    if "link" in role or "hyperlink" in role:
                        node_text = node.get("text", "")
                        # screenpipe: extract URL if text starts with http/https
                        for url in self._extract_urls_from_link_text(node_text):
                            if url not in urls:
                                urls.append(url)

                # Extract URLs from full text using regex (aligns with screenpipe)
                # screenpipe: word-based scan with length > 10 check and punctuation trimming
                for url in self._extract_urls_from_text(text):
                    if url not in urls:
                        urls.append(url)

                # Apply truncation (screenpipe-aligned defaults: text=2000, nodes=50)
                result_text = text
                if max_text_length is not None and len(result_text) > max_text_length:
                    result_text = result_text[:max_text_length] + "..."

                result_nodes = nodes
                if max_nodes is not None and len(nodes) > max_nodes:
                    nodes_truncated = len(nodes) - max_nodes
                    result_nodes = nodes[:max_nodes]

                result = {
                    "frame_id": frame_id_val,
                    "text": result_text,
                    "text_source": text_source,
                    "nodes": result_nodes,
                    "urls": urls,
                    "browser_url": browser_url,
                    "status": status,
                }

                if nodes_truncated is not None:
                    result["nodes_truncated"] = nodes_truncated

                return result

        except sqlite3.Error as e:
            logger.error("get_frame_context failed frame_id=%d: %s", frame_id, e)
            return None

    def _extract_urls_from_link_text(self, text: str) -> list[str]:
        """Extract URLs from link node text (screenpipe-aligned).

        screenpipe behavior: extract URL only if the trimmed text starts with http/https.
        Takes just the URL part (stops at whitespace).
        """
        trimmed = text.strip()
        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            # Take just the URL part (stop at whitespace)
            url = trimmed.split()[0] if trimmed.split() else trimmed
            return [url]
        return []

    def _extract_urls_from_text(self, text: str) -> list[str]:
        """Extract URLs from text using regex (screenpipe-aligned).

        screenpipe behavior:
        - Split by whitespace
        - Trim punctuation: , ) ] > " '
        - Must start with http:// or https://
        - Length must be > 10
        """
        urls = []
        for word in text.split():
            # Trim punctuation (screenpipe: `, ) ] > " '`)
            trimmed = word.strip(',)]>"\'')
            if (trimmed.startswith("http://") or trimmed.startswith("https://")) and len(trimmed) > 10:
                urls.append(trimmed)
        return urls
