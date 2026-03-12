"""v3 FramesStore: SQLite-backed store for the `frames` table."""

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
        )

    def _extract_metadata_fields(
        self, metadata: dict[str, object]
    ) -> tuple[
        object,
        object,
        object,
        object,
        object,
        object,
        object,
        object,
        object,
        object,
        object,
    ]:
        raw_timestamp = metadata.get("timestamp") or metadata.get("capture_time")
        timestamp = _to_utc_iso8601(raw_timestamp) or ""
        app_name = metadata.get("app_name") or metadata.get("app")
        window_name = metadata.get("window_name") or metadata.get("window")
        browser_url = metadata.get("browser_url")
        focused = metadata.get("focused")
        device_name = metadata.get("device_name") or "monitor_0"
        capture_trigger = metadata.get("capture_trigger")
        event_ts = _to_utc_iso8601(metadata.get("event_ts"))
        image_size_bytes = metadata.get("image_size_bytes")
        accessibility_text = metadata.get("accessibility_text")
        content_hash = metadata.get("content_hash")
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
            accessibility_text,
            content_hash,
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
            accessibility_text,
            content_hash,
        ) = self._extract_metadata_fields(metadata)

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO frames
                        (capture_id, timestamp, app_name, window_name, browser_url,
                         focused, device_name, capture_trigger, event_ts, snapshot_path,
                         image_size_bytes, accessibility_text, content_hash, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
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
                        accessibility_text,
                        content_hash,
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
                           snapshot_path, status, ingested_at, image_size_bytes, error_message
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
                           snapshot_path, status, ingested_at, image_size_bytes, error_message
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
        """
        memories = []
        normalized_limit = max(1, min(int(limit) if limit else 500, 1000))

        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, capture_id, timestamp, app_name, window_name,
                           snapshot_path, status, ingested_at
                    FROM frames
                    ORDER BY timestamp DESC
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
                           snapshot_path, status, ingested_at
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
        """
        memories = []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, capture_id, timestamp, app_name, window_name,
                           snapshot_path, status, ingested_at
                    FROM frames
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
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
