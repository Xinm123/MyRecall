import logging
import sqlite3
import numpy as np
from typing import Any, List, Optional, Tuple
from pathlib import Path

from openrecall.shared.config import settings
from openrecall.shared.models import RecallEntry

logger = logging.getLogger(__name__)

class SQLStore:
    """
    Unified SQL Store for OpenRecall.
    Manages:
    1. Task Queue & Metadata (in recall.db / db_path)
    2. Full-Text Search (in fts.db / fts_path)
    """

    def __init__(self):
        self.db_path = settings.db_path
        self.fts_path = settings.fts_path
        self._video_chunk_columns_cache: Optional[set[str]] = None
        self._init_db()

    def _init_db(self):
        """Initialize both databases and their tables."""
        # 1. Initialize Task/Metadata DB
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS entries (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           app TEXT,
                           title TEXT,
                           text TEXT,
                           timestamp INTEGER UNIQUE,
                           embedding BLOB,
                           description TEXT,
                           status TEXT DEFAULT 'COMPLETED'
                       )"""
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)"
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize metadata database: {e}")
            # We don't raise here to allow partial functionality if DB exists but locked?
            # But mostly we should raise.
            raise

        # 2. Initialize FTS DB
        try:
            with sqlite3.connect(str(self.fts_path)) as conn:
                conn.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts 
                       USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)"""
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize FTS database: {e}")
            raise

        # 3. Apply schema migrations (idempotent)
        self._run_migrations()

    def _run_migrations(self) -> None:
        """Apply DB migrations so runtime schema matches current code paths."""
        from openrecall.server.database.migrations.runner import MigrationRunner

        result = MigrationRunner(self.db_path).run()
        if not result.success:
            raise RuntimeError(f"Database migration failed: {result.error or 'unknown error'}")
        self._video_chunk_columns_cache = None
        logger.info(
            "Database migrations ensured (version=%s, elapsed=%.3fs)",
            result.version,
            result.elapsed_seconds,
        )

    # =========================================================================
    # FTS Methods
    # =========================================================================

    def add_document(self, snapshot_id: str, ocr_text: str, caption: str, keywords: List[str]):
        """Add a document to the FTS index."""
        keywords_str = " ".join(keywords)
        try:
            with sqlite3.connect(str(self.fts_path)) as conn:
                conn.execute(
                    "INSERT INTO ocr_fts (snapshot_id, ocr_text, caption, keywords) VALUES (?, ?, ?, ?)",
                    (str(snapshot_id), ocr_text, caption, keywords_str)
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to add document to FTS: {e}")

    def search(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        """Search for documents matching the query. Returns list of (snapshot_id, bm25_score)."""
        try:
            with sqlite3.connect(str(self.fts_path)) as conn:
                cursor = conn.execute(
                    "SELECT snapshot_id, bm25(ocr_fts) AS score "
                    "FROM ocr_fts "
                    "WHERE ocr_fts MATCH ? "
                    "ORDER BY score ASC "
                    "LIMIT ?",
                    (query, limit),
                )
                return [(row[0], float(row[1])) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"FTS search failed: {e}")
            return []

    # =========================================================================
    # Task Queue & Metadata Methods
    # =========================================================================

    def _row_to_entry(self, row: sqlite3.Row) -> RecallEntry:
        """Convert a database row to RecallEntry."""
        try:
            status = row["status"]
        except (KeyError, IndexError):
            status = "COMPLETED"
        
        return RecallEntry(
            id=row["id"],
            app=row["app"],
            title=row["title"],
            text=row["text"],
            description=row["description"],
            timestamp=row["timestamp"],
            embedding=row["embedding"],
            status=status,
        )

    def insert_pending_entry(self, timestamp: int, app: str, title: str, image_path: str) -> Optional[int]:
        """Insert a PENDING entry for async processing."""
        last_row_id: Optional[int] = None
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO entries (timestamp, app, title, status)
                       VALUES (?, ?, ?, 'PENDING')
                       ON CONFLICT(timestamp) DO NOTHING""",
                    (timestamp, app, title),
                )
                conn.commit()
                if cursor.rowcount > 0:
                    last_row_id = cursor.lastrowid
                    logger.info(f"Fast ingestion: Inserted PENDING entry (id={last_row_id}, ts={timestamp})")
                else:
                    logger.warning(f"Duplicate timestamp skipped: {timestamp}")
        except sqlite3.Error as e:
            logger.error(f"Database error during fast ingestion: {e}")
        return last_row_id

    def get_pending_count(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Count the number of pending tasks."""
        count = 0
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM entries WHERE status='PENDING'")
                    count = cursor.fetchone()[0]
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM entries WHERE status='PENDING'")
                count = cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Database error while counting pending tasks: {e}")
        return count

    def get_next_task(self, conn: sqlite3.Connection, lifo_mode: bool = False) -> Optional[RecallEntry]:
        """Get the next pending task to process."""
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            order = "DESC" if lifo_mode else "ASC"
            cursor.execute(
                f"SELECT id, app, title, text, description, timestamp, embedding, status "
                f"FROM entries WHERE status IN ('PENDING', 'CANCELLED') ORDER BY timestamp {order} LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_entry(row)
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching next task: {e}")
        return None

    def mark_task_processing(self, conn: sqlite3.Connection, task_id: int) -> bool:
        """Mark a task as currently being processed."""
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE entries SET status='PROCESSING' WHERE id=?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error while marking task {task_id} as processing: {e}")
            return False

    def mark_task_cancelled_if_processing(self, conn: sqlite3.Connection, task_id: int) -> bool:
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE entries SET status='CANCELLED' WHERE id=? AND status='PROCESSING'", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error while cancelling task {task_id}: {e}")
            return False

    def mark_task_completed(self, conn: sqlite3.Connection, task_id: int, text: str, description: Optional[str], embedding: np.ndarray) -> bool:
        """Mark a task as completed with processing results."""
        try:
            embedding_bytes = embedding.astype(np.float32).tobytes()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE entries SET text=?, description=?, embedding=?, status='COMPLETED' "
                "WHERE id=? AND status IN ('PROCESSING', 'PENDING')",
                (text, description, embedding_bytes, task_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error while marking task {task_id} as completed: {e}")
            return False

    def mark_task_failed(self, conn: sqlite3.Connection, task_id: int) -> bool:
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE entries SET status='FAILED' WHERE id=?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error while marking task {task_id} as failed: {e}")
            return False

    def reset_stuck_tasks(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Reset tasks stuck in PROCESSING state back to PENDING."""
        count = 0
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE entries SET status='PENDING' WHERE status='PROCESSING'")
                    count = cursor.rowcount
                    conn.commit()
            else:
                cursor = conn.cursor()
                cursor.execute("UPDATE entries SET status='PENDING' WHERE status='PROCESSING'")
                count = cursor.rowcount
                conn.commit()
            
            if count > 0:
                logger.info(f"Reset {count} stuck tasks from PROCESSING to PENDING")
        except sqlite3.Error as e:
            logger.error(f"Database error while resetting stuck tasks: {e}")
        return count

    def cancel_processing_tasks(self, conn: Optional[sqlite3.Connection] = None) -> int:
        count = 0
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE entries SET status='CANCELLED' WHERE status='PROCESSING'")
                    count = cursor.rowcount
                    conn.commit()
            else:
                cursor = conn.cursor()
                cursor.execute("UPDATE entries SET status='CANCELLED' WHERE status='PROCESSING'")
                count = cursor.rowcount
                conn.commit()
            if count > 0:
                logger.info(f"Cancelled {count} processing tasks")
        except sqlite3.Error as e:
            logger.error(f"Database error while cancelling processing tasks: {e}")
        return count

    def get_all_entries_with_status(self) -> List[RecallEntry]:
        """Retrieves ALL entries from the database regardless of status."""
        entries: List[RecallEntry] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, app, title, text, description, timestamp, embedding, status FROM entries "
                    "ORDER BY timestamp DESC"
                )
                entries = [self._row_to_entry(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching all entries with status: {e}")
        return entries

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        """Return True when a table/view exists in the metadata DB."""
        try:
            cursor = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=? LIMIT 1",
                (table_name,),
            )
            return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    def _fetch_entry_memories(
        self,
        conn: sqlite3.Connection,
        limit: Optional[int] = None,
        since: Optional[float] = None,
    ) -> List[dict]:
        """Fetch legacy screenshot memories from entries table."""
        memories: List[dict] = []
        cursor = conn.cursor()
        if since is None:
            sql = (
                "SELECT id, app, title, text, description, timestamp, status "
                "FROM entries ORDER BY timestamp DESC LIMIT ?"
            )
            cursor.execute(sql, (limit if limit is not None else 200,))
        else:
            sql = (
                "SELECT id, app, title, text, description, timestamp, status "
                "FROM entries WHERE timestamp > ? ORDER BY timestamp DESC"
            )
            cursor.execute(sql, (since,))

        for row in cursor.fetchall():
            ts = float(row["timestamp"])
            image_name = f"{int(ts)}.png"
            image_path = settings.screenshots_path / image_name
            # Skip corrupted/invalid screenshot artifacts (e.g. video bytes saved as .png).
            try:
                if not image_path.exists():
                    continue
                with open(image_path, "rb") as image_file:
                    if image_file.read(8) != b"\x89PNG\r\n\x1a\n":
                        continue
            except OSError:
                continue
            memories.append(
                {
                    "id": row["id"],
                    "timestamp": ts,
                    "app": row["app"],
                    "title": row["title"],
                    "text": row["text"],
                    "description": row["description"],
                    "status": row["status"] if "status" in row.keys() else "COMPLETED",
                    "filename": image_name,
                    "image_url": f"/screenshots/{image_name}",
                    "app_name": row["app"],
                    "window_title": row["title"],
                }
            )
        return memories

    def _fetch_frame_memories(
        self,
        conn: sqlite3.Connection,
        limit: Optional[int] = None,
        since: Optional[float] = None,
    ) -> List[dict]:
        """Fetch video-frame memories from frames table."""
        memories: List[dict] = []
        if not self._table_exists(conn, "frames"):
            return memories

        cursor = conn.cursor()
        if since is None:
            sql = (
                "SELECT f.id AS frame_id, f.video_chunk_id, f.timestamp, f.app_name, f.window_name, "
                "f.focused, f.browser_url, ot.text AS ocr_text "
                "FROM frames f LEFT JOIN ocr_text ot ON ot.frame_id = f.id "
                "ORDER BY f.timestamp DESC LIMIT ?"
            )
            cursor.execute(sql, (limit if limit is not None else 200,))
        else:
            sql = (
                "SELECT f.id AS frame_id, f.video_chunk_id, f.timestamp, f.app_name, f.window_name, "
                "f.focused, f.browser_url, ot.text AS ocr_text "
                "FROM frames f LEFT JOIN ocr_text ot ON ot.frame_id = f.id "
                "WHERE f.timestamp > ? ORDER BY f.timestamp DESC"
            )
            cursor.execute(sql, (since,))

        for row in cursor.fetchall():
            frame_id = int(row["frame_id"])
            ts = float(row["timestamp"])
            ocr_text = row["ocr_text"] or ""
            raw_focused = row["focused"]
            focused_val = bool(raw_focused) if raw_focused is not None else None
            raw_url = row["browser_url"]
            browser_url_val = raw_url if raw_url else None
            memories.append(
                {
                    "id": f"frame-{frame_id}",
                    "timestamp": ts,
                    "app": row["app_name"] or "Unknown",
                    "title": row["window_name"] or "Unknown",
                    "text": ocr_text,
                    "description": ocr_text[:300] if ocr_text else "",
                    "status": "COMPLETED",
                    "filename": None,
                    "image_url": f"/api/v1/frames/{frame_id}",
                    "frame_id": frame_id,
                    "video_chunk_id": row["video_chunk_id"],
                    "app_name": row["app_name"] or "Unknown",
                    "window_title": row["window_name"] or "Unknown",
                    "focused": focused_val,
                    "browser_url": browser_url_val,
                }
            )
        return memories

    def _merge_memories(self, entries: List[dict], frames: List[dict], limit: Optional[int]) -> List[dict]:
        """Merge two memory lists by timestamp descending."""
        merged = entries + frames
        merged.sort(key=lambda item: float(item.get("timestamp", 0.0)), reverse=True)
        if limit is None:
            return merged
        return merged[:limit]

    def get_timestamps(self) -> List[int]:
        """Retrieves all timestamps from the database."""
        timestamps: List[int] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp FROM entries ORDER BY timestamp DESC")
                results = cursor.fetchall()
                timestamps = [result[0] for result in results]
                if self._table_exists(conn, "frames"):
                    cursor.execute("SELECT timestamp FROM frames ORDER BY timestamp DESC")
                    frame_ts = [int(float(result[0])) for result in cursor.fetchall()]
                    timestamps.extend(frame_ts)
                    timestamps = sorted(set(timestamps), reverse=True)
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching timestamps: {e}")
        return timestamps

    def get_recent_memories(self, limit: int = 200) -> List[dict]:
        """Retrieves recent memories for API."""
        memories: List[dict] = []
        normalized_limit = max(1, min(int(limit) if limit else 200, 1000))

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                entry_memories = self._fetch_entry_memories(conn, limit=normalized_limit)
                frame_memories = self._fetch_frame_memories(conn, limit=normalized_limit)
                memories = self._merge_memories(entry_memories, frame_memories, normalized_limit)
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching recent memories: {e}")
        return memories

    def get_memories_since(self, timestamp: float) -> List[dict]:
        """Retrieves entries with timestamp > timestamp."""
        memories: List[dict] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                entry_memories = self._fetch_entry_memories(conn, since=timestamp)
                frame_memories = self._fetch_frame_memories(conn, since=timestamp)
                memories = self._merge_memories(entry_memories, frame_memories, limit=None)
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching memories since time: {e}")
        return memories

    # =========================================================================
    # Phase 1: Video Chunk Methods
    # =========================================================================

    def get_video_chunk_status_counts(self, conn: Optional[sqlite3.Connection] = None) -> dict[str, int]:
        """Get video_chunks count grouped by status.

        Returns empty counts when the table does not exist yet.
        """
        counts: dict[str, int] = {}
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as local_conn:
                    if not self._table_exists(local_conn, "video_chunks"):
                        return counts
                    cursor = local_conn.cursor()
                    cursor.execute("SELECT status, COUNT(*) FROM video_chunks GROUP BY status")
                    counts = {str(status): int(count) for status, count in cursor.fetchall()}
            else:
                if not self._table_exists(conn, "video_chunks"):
                    return counts
                cursor = conn.cursor()
                cursor.execute("SELECT status, COUNT(*) FROM video_chunks GROUP BY status")
                counts = {str(status): int(count) for status, count in cursor.fetchall()}
        except sqlite3.Error as e:
            logger.error(f"Failed to get video chunk status counts: {e}")
        return counts

    def insert_video_chunk(
        self,
        file_path: str,
        device_name: str = "",
        checksum: Optional[str] = None,
        retention_days: Optional[int] = None,
        app_name: str = "",
        window_name: str = "",
        monitor_id: str = "",
        monitor_width: int = 0,
        monitor_height: int = 0,
        monitor_is_primary: int = 0,
        monitor_backend: str = "",
        monitor_fingerprint: str = "",
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Optional[int]:
        """Insert a new video chunk with PENDING status."""
        days = retention_days if retention_days is not None else settings.retention_days
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                columns = self._get_video_chunk_columns(conn)
                insert_columns = ["file_path", "device_name", "checksum", "status", "expires_at"]
                value_fragments = ["?", "?", "?", "?", "datetime('now', ?)"]
                values = [file_path, device_name, checksum, "PENDING", f"+{days} days"]

                optional_values = {
                    "app_name": app_name,
                    "window_name": window_name,
                    "monitor_id": monitor_id,
                    "monitor_width": monitor_width,
                    "monitor_height": monitor_height,
                    "monitor_is_primary": monitor_is_primary,
                    "monitor_backend": monitor_backend,
                    "monitor_fingerprint": monitor_fingerprint,
                    "start_time": start_time,
                    "end_time": end_time,
                }
                for column, value in optional_values.items():
                    if column in columns:
                        insert_columns.append(column)
                        value_fragments.append("?")
                        values.append(value)

                sql = (
                    f"INSERT INTO video_chunks ({', '.join(insert_columns)}) "
                    f"VALUES ({', '.join(value_fragments)})"
                )
                cursor.execute(sql, values)
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to insert video chunk: {e}")
            return None

    def _get_video_chunk_columns(self, conn: sqlite3.Connection) -> set[str]:
        """Get video_chunks table column names with lazy cache."""
        if self._video_chunk_columns_cache is not None:
            return self._video_chunk_columns_cache
        cursor = conn.execute("PRAGMA table_info(video_chunks)")
        self._video_chunk_columns_cache = {row[1] for row in cursor.fetchall()}
        return self._video_chunk_columns_cache

    def get_video_chunk_by_id(self, chunk_id: int) -> Optional[dict]:
        """Get a video chunk by its ID."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM video_chunks WHERE id=?", (chunk_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get video chunk {chunk_id}: {e}")
            return None

    def get_next_pending_video_chunk(self, conn: sqlite3.Connection) -> Optional[dict]:
        """Get the next pending video chunk for processing (FIFO)."""
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_chunks WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1"
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get next pending video chunk: {e}")
            return None

    def mark_video_chunk_processing(self, conn: sqlite3.Connection, chunk_id: int) -> bool:
        """Mark a video chunk as PROCESSING."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE video_chunks SET status='PROCESSING' WHERE id=? AND status='PENDING'",
                (chunk_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark video chunk {chunk_id} as processing: {e}")
            return False

    def mark_video_chunk_completed(self, conn: sqlite3.Connection, chunk_id: int) -> bool:
        """Mark a video chunk as COMPLETED."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE video_chunks SET status='COMPLETED' WHERE id=? AND status='PROCESSING'",
                (chunk_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark video chunk {chunk_id} as completed: {e}")
            return False

    def mark_video_chunk_failed(self, conn: sqlite3.Connection, chunk_id: int) -> bool:
        """Mark a video chunk as FAILED."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE video_chunks SET status='FAILED' WHERE id=? AND status='PROCESSING'",
                (chunk_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark video chunk {chunk_id} as failed: {e}")
            return False

    def reset_stuck_video_chunks(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Reset video chunks stuck in PROCESSING back to PENDING."""
        count = 0
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE video_chunks SET status='PENDING' WHERE status='PROCESSING'")
                    count = cursor.rowcount
                    conn.commit()
            else:
                cursor = conn.cursor()
                cursor.execute("UPDATE video_chunks SET status='PENDING' WHERE status='PROCESSING'")
                count = cursor.rowcount
                conn.commit()

            if count > 0:
                logger.info(f"Reset {count} stuck video chunks from PROCESSING to PENDING")
        except sqlite3.Error as e:
            logger.error(f"Failed to reset stuck video chunks: {e}")
        return count

    # =========================================================================
    # Phase 1: Frame Methods
    # =========================================================================

    def insert_frame(
        self, video_chunk_id: int, offset_index: int, timestamp: float,
        app_name: Optional[str] = None, window_name: Optional[str] = None,
        focused: Optional[bool] = None, browser_url: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a single frame record."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                focused_val = (1 if focused else 0) if focused is not None else None
                cursor.execute(
                    """INSERT INTO frames (video_chunk_id, offset_index, timestamp,
                                          app_name, window_name, focused, browser_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (video_chunk_id, offset_index, timestamp,
                     app_name, window_name, focused_val, browser_url),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to insert frame: {e}")
            return None

    def insert_frames_batch(self, frames: list) -> List[int]:
        """Insert multiple frames in a single transaction. Returns list of frame IDs."""
        frame_ids: List[int] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                for frame in frames:
                    raw_focused = frame.get("focused")
                    focused_val = (1 if raw_focused else 0) if raw_focused is not None else None
                    cursor.execute(
                        """INSERT INTO frames (video_chunk_id, offset_index, timestamp,
                                              app_name, window_name, focused, browser_url)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            frame["video_chunk_id"],
                            frame["offset_index"],
                            frame["timestamp"],
                            frame.get("app_name"),
                            frame.get("window_name"),
                            focused_val,
                            frame.get("browser_url"),
                        ),
                    )
                    frame_ids.append(cursor.lastrowid)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to insert frames batch: {e}")
        return frame_ids

    def get_frame_by_id(self, frame_id: int) -> Optional[dict]:
        """Get a frame by ID, including the parent chunk's file_path."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT f.*, vc.file_path AS chunk_path
                       FROM frames f
                       JOIN video_chunks vc ON f.video_chunk_id = vc.id
                       WHERE f.id=?""",
                    (frame_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get frame {frame_id}: {e}")
            return None

    def query_frames_by_time_range(
        self, start_time: float, end_time: float, limit: int = 50, offset: int = 0,
    ) -> Tuple[list, int]:
        """Query frames within a time range with pagination. Returns (frames, total)."""
        frames: list = []
        total = 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Count total
                cursor.execute(
                    "SELECT COUNT(*) FROM frames WHERE timestamp >= ? AND timestamp <= ?",
                    (start_time, end_time),
                )
                total = cursor.fetchone()[0]
                # Fetch page with OCR text
                cursor.execute(
                    """SELECT f.id AS frame_id, f.video_chunk_id, f.offset_index, f.timestamp,
                              f.app_name, f.window_name, f.focused, f.browser_url,
                              ot.text AS ocr_text
                       FROM frames f
                       LEFT JOIN ocr_text ot ON f.id = ot.frame_id
                       WHERE f.timestamp >= ? AND f.timestamp <= ?
                       ORDER BY f.timestamp ASC
                       LIMIT ? OFFSET ?""",
                    (start_time, end_time, limit, offset),
                )
                for row in cursor.fetchall():
                    d = dict(row)
                    d["frame_url"] = f"/api/v1/frames/{d['frame_id']}"
                    # Normalize focused: NULL -> None, 0 -> False, 1 -> True
                    raw_focused = d.get("focused")
                    d["focused"] = bool(raw_focused) if raw_focused is not None else None
                    # Normalize browser_url: empty string -> None
                    raw_url = d.get("browser_url")
                    d["browser_url"] = raw_url if raw_url else None
                    frames.append(d)
        except sqlite3.Error as e:
            logger.error(f"Failed to query frames by time range: {e}")
        return frames, total

    # =========================================================================
    # Phase 1: OCR Text Methods
    # =========================================================================

    def insert_ocr_text(
        self, frame_id: int, text: str, text_json: Optional[str] = None,
        ocr_engine: str = "rapidocr", text_length: Optional[int] = None,
    ) -> None:
        """Insert OCR text for a frame."""
        length = text_length if text_length is not None else len(text)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO ocr_text (frame_id, text, text_json, ocr_engine, text_length)
                       VALUES (?, ?, ?, ?, ?)""",
                    (frame_id, text, text_json, ocr_engine, length),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to insert OCR text for frame {frame_id}: {e}")

    def insert_ocr_text_fts(
        self, frame_id: int, text: str, app_name: str = "", window_name: str = "",
    ) -> None:
        """Insert into the ocr_text_fts FTS5 virtual table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO ocr_text_fts (text, app_name, window_name, frame_id) VALUES (?, ?, ?, ?)",
                    (text, app_name, window_name, frame_id),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to insert FTS for frame {frame_id}: {e}")

    # =========================================================================
    # Phase 1: Video FTS Search
    # =========================================================================

    def search_video_fts(self, query: str, limit: int = 10) -> list:
        """Search video frame OCR text via FTS5. Returns list of dicts."""
        results: list = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT fts.frame_id, fts.app_name, fts.window_name,
                              snippet(ocr_text_fts, 0, '<b>', '</b>', '...', 32) AS text_snippet,
                              bm25(ocr_text_fts) AS score,
                              f.timestamp, f.video_chunk_id, f.offset_index,
                              f.focused, f.browser_url
                       FROM ocr_text_fts fts
                       JOIN frames f ON fts.frame_id = f.id
                       WHERE ocr_text_fts MATCH ?
                       ORDER BY score ASC
                       LIMIT ?""",
                    (query, limit),
                )
                for row in cursor.fetchall():
                    d = dict(row)
                    # Normalize focused: NULL -> None, 0 -> False, 1 -> True
                    raw_focused = d.get("focused")
                    d["focused"] = bool(raw_focused) if raw_focused is not None else None
                    # Normalize browser_url: empty string -> None
                    raw_url = d.get("browser_url")
                    d["browser_url"] = raw_url if raw_url else None
                    results.append(d)
        except sqlite3.Error as e:
            logger.error(f"Video FTS search failed: {e}")
        return results

    # =========================================================================
    # Phase 1: Retention Methods
    # =========================================================================

    def get_expired_video_chunks(self) -> list:
        """Get video chunks that have expired and are completed."""
        results: list = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM video_chunks WHERE expires_at < datetime('now') AND status='COMPLETED'"
                )
                results = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get expired video chunks: {e}")
        return results

    def delete_video_chunk_cascade(self, chunk_id: int) -> int:
        """Delete a video chunk and all associated data. Returns number of frames deleted."""
        frames_deleted = 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                cursor = conn.cursor()
                # First delete FTS entries (not covered by CASCADE)
                cursor.execute(
                    "DELETE FROM ocr_text_fts WHERE frame_id IN (SELECT id FROM frames WHERE video_chunk_id=?)",
                    (chunk_id,),
                )
                # Count frames before cascade delete
                cursor.execute("SELECT COUNT(*) FROM frames WHERE video_chunk_id=?", (chunk_id,))
                frames_deleted = cursor.fetchone()[0]
                # CASCADE handles frames + ocr_text
                cursor.execute("DELETE FROM video_chunks WHERE id=?", (chunk_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to cascade delete video chunk {chunk_id}: {e}")
        return frames_deleted

    def get_expired_entries(self) -> list:
        """Get screenshot entries that have expired."""
        results: list = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM entries WHERE expires_at IS NOT NULL AND expires_at != '' AND expires_at < datetime('now')"
                )
                results = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get expired entries: {e}")
        return results

    # =========================================================================
    # Phase 2: Audio Chunk Methods
    # =========================================================================

    def get_audio_chunk_status_counts(self, conn: Optional[sqlite3.Connection] = None) -> dict[str, int]:
        """Get audio_chunks count grouped by status."""
        counts: dict[str, int] = {}
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as local_conn:
                    if not self._table_exists(local_conn, "audio_chunks"):
                        return counts
                    cursor = local_conn.cursor()
                    cursor.execute("SELECT status, COUNT(*) FROM audio_chunks GROUP BY status")
                    counts = {str(status): int(count) for status, count in cursor.fetchall()}
            else:
                if not self._table_exists(conn, "audio_chunks"):
                    return counts
                cursor = conn.cursor()
                cursor.execute("SELECT status, COUNT(*) FROM audio_chunks GROUP BY status")
                counts = {str(status): int(count) for status, count in cursor.fetchall()}
        except sqlite3.Error as e:
            logger.error(f"Failed to get audio chunk status counts: {e}")
        return counts

    @staticmethod
    def _infer_audio_source_kind(device_name: str) -> str:
        """Infer source kind (input/output/unknown) from device name."""
        name = (device_name or "").strip().lower()
        if not name:
            return "unknown"
        if any(token in name for token in ("mic", "microphone", "input")):
            return "input"
        if any(token in name for token in ("system", "speaker", "loopback", "output")):
            return "output"
        return "unknown"

    @staticmethod
    def _normalize_audio_source_kind(source_kind: Optional[str], device_name: str) -> str:
        """Normalize source kind with fallback inference from device name."""
        raw = (source_kind or "").strip().lower()
        if raw in {"input", "output", "unknown"}:
            return raw
        return SQLStore._infer_audio_source_kind(device_name)

    @staticmethod
    def _normalize_is_input(is_input: Optional[bool], source_kind: str) -> Optional[int]:
        """Normalize is_input to SQLite-friendly integer/null."""
        if is_input is True:
            return 1
        if is_input is False:
            return 0
        if source_kind == "input":
            return 1
        if source_kind == "output":
            return 0
        return None

    def insert_audio_chunk(
        self,
        file_path: str,
        timestamp: float,
        device_name: str = "",
        checksum: Optional[str] = None,
        retention_days: Optional[int] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        is_input: Optional[bool] = None,
        source_kind: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a new audio chunk with PENDING status."""
        days = retention_days if retention_days is not None else settings.retention_days
        normalized_source = self._normalize_audio_source_kind(source_kind, device_name)
        normalized_is_input = self._normalize_is_input(is_input, normalized_source)
        chunk_start_time = float(start_time if start_time is not None else timestamp)
        chunk_end_time = float(end_time if end_time is not None else timestamp)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO audio_chunks (
                           file_path, timestamp, start_time, end_time,
                           device_name, is_input, source_kind,
                           checksum, status, expires_at
                       )
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', datetime('now', ?))""",
                    (
                        file_path,
                        timestamp,
                        chunk_start_time,
                        chunk_end_time,
                        device_name,
                        normalized_is_input,
                        normalized_source,
                        checksum,
                        f"+{days} days",
                    ),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to insert audio chunk: {e}")
            return None

    def get_audio_chunk_by_id(self, chunk_id: int) -> Optional[dict]:
        """Get an audio chunk by its ID."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM audio_chunks WHERE id=?", (chunk_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get audio chunk {chunk_id}: {e}")
            return None

    def get_next_pending_audio_chunk(self, conn: sqlite3.Connection) -> Optional[dict]:
        """Get the next pending audio chunk for processing (FIFO)."""
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audio_chunks WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1"
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get next pending audio chunk: {e}")
            return None

    def mark_audio_chunk_processing(self, conn: sqlite3.Connection, chunk_id: int) -> bool:
        """Mark an audio chunk as PROCESSING."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audio_chunks SET status='PROCESSING' WHERE id=? AND status='PENDING'",
                (chunk_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark audio chunk {chunk_id} as processing: {e}")
            return False

    def mark_audio_chunk_completed(self, conn: sqlite3.Connection, chunk_id: int) -> bool:
        """Mark an audio chunk as COMPLETED."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audio_chunks SET status='COMPLETED' WHERE id=? AND status='PROCESSING'",
                (chunk_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark audio chunk {chunk_id} as completed: {e}")
            return False

    def mark_audio_chunk_failed(self, conn: sqlite3.Connection, chunk_id: int) -> bool:
        """Mark an audio chunk as FAILED and increment retry_count."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audio_chunks SET status='FAILED', retry_count=COALESCE(retry_count,0)+1 WHERE id=?",
                (chunk_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark audio chunk {chunk_id} as failed: {e}")
            return False

    def reset_stuck_audio_chunks(self, conn: Optional[sqlite3.Connection] = None, max_retries: int = 3) -> int:
        """Reset audio chunks stuck in PROCESSING back to PENDING.

        Chunks that have exceeded max_retries stay as FAILED.
        """
        count = 0
        sql = "UPDATE audio_chunks SET status='PENDING' WHERE status='PROCESSING' AND COALESCE(retry_count,0) < ?"
        try:
            if conn is None:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql, (max_retries,))
                    count = cursor.rowcount
                    conn.commit()
            else:
                cursor = conn.cursor()
                cursor.execute(sql, (max_retries,))
                count = cursor.rowcount
                conn.commit()

            if count > 0:
                logger.info(f"Reset {count} stuck audio chunks from PROCESSING to PENDING")
        except sqlite3.Error as e:
            logger.error(f"Failed to reset stuck audio chunks: {e}")
        return count

    # =========================================================================
    # Phase 2: Audio Transcription Methods
    # =========================================================================

    def insert_audio_transcription(
        self,
        audio_chunk_id: int,
        offset_index: int,
        timestamp: float,
        transcription: str,
        transcription_engine: str = "",
        speaker_id: Optional[int] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Optional[int]:
        """Insert a transcription record for an audio chunk."""
        text_length = len(transcription)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO audio_transcriptions
                       (audio_chunk_id, offset_index, timestamp, transcription,
                        transcription_engine, speaker_id, start_time, end_time, text_length)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (audio_chunk_id, offset_index, timestamp, transcription,
                     transcription_engine, speaker_id, start_time, end_time, text_length),
                )
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to insert audio transcription for chunk {audio_chunk_id}: {e}")
            return None

    def insert_audio_transcription_fts(
        self,
        transcription: str,
        device: str = "",
        audio_chunk_id: Optional[int] = None,
        speaker_id: Optional[int] = None,
        transcription_id: Optional[int] = None,
    ) -> None:
        """Insert into the audio_transcriptions_fts FTS5 virtual table.

        Args:
            transcription_id: If provided, set as the FTS rowid to enable
                              1:1 join with audio_transcriptions.id.
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                if transcription_id is not None:
                    conn.execute(
                        "INSERT INTO audio_transcriptions_fts (rowid, transcription, device, audio_chunk_id, speaker_id) VALUES (?, ?, ?, ?, ?)",
                        (transcription_id, transcription, device, audio_chunk_id, speaker_id),
                    )
                else:
                    conn.execute(
                        "INSERT INTO audio_transcriptions_fts (transcription, device, audio_chunk_id, speaker_id) VALUES (?, ?, ?, ?)",
                        (transcription, device, audio_chunk_id, speaker_id),
                    )
        except sqlite3.Error as e:
            logger.error(f"Failed to insert audio FTS for chunk {audio_chunk_id}: {e}")

    def insert_audio_transcription_with_fts(
        self,
        audio_chunk_id: int,
        offset_index: int,
        timestamp: float,
        transcription: str,
        transcription_engine: str = "",
        speaker_id: Optional[int] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        device: str = "",
    ) -> Optional[int]:
        """Insert transcription + FTS atomically in a single transaction."""
        text_length = len(transcription)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO audio_transcriptions
                       (audio_chunk_id, offset_index, timestamp, transcription,
                        transcription_engine, speaker_id, start_time, end_time, text_length)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (audio_chunk_id, offset_index, timestamp, transcription,
                     transcription_engine, speaker_id, start_time, end_time, text_length),
                )
                trans_id = cursor.lastrowid
                if trans_id:
                    conn.execute(
                        "INSERT INTO audio_transcriptions_fts "
                        "(rowid, transcription, device, audio_chunk_id, speaker_id) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (trans_id, transcription, device, audio_chunk_id, speaker_id),
                    )
                conn.commit()
                return trans_id
        except sqlite3.Error as e:
            logger.error(f"Failed to insert audio transcription+FTS for chunk {audio_chunk_id}: {e}")
            return None

    # =========================================================================
    # Phase 2: Audio FTS Search
    # =========================================================================

    def search_audio_fts(self, query: str, limit: int = 10) -> list:
        """Search audio transcriptions via FTS5. Returns list of dicts.

        Join uses fts.rowid = at.id for 1:1 mapping (requires insert_audio_transcription_fts
        to be called with transcription_id). Column aliases match API expectations.
        """
        results: list = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT at.id, at.audio_chunk_id, at.timestamp,
                              at.start_time, at.end_time, at.transcription,
                              at.transcription_engine,
                              fts.device AS device_name, fts.speaker_id,
                              snippet(audio_transcriptions_fts, 0, '<b>', '</b>', '...', 32) AS snippet,
                              bm25(audio_transcriptions_fts) AS score
                       FROM audio_transcriptions_fts fts
                       JOIN audio_transcriptions at ON fts.rowid = at.id
                       WHERE audio_transcriptions_fts MATCH ?
                       ORDER BY score ASC
                       LIMIT ?""",
                    (query, limit),
                )
                for row in cursor.fetchall():
                    results.append(dict(row))
        except sqlite3.Error as e:
            logger.error(f"Audio FTS search failed: {e}")
        return results

    def get_audio_transcriptions_by_time_range(
        self, start_time: float, end_time: float, limit: int = 50, offset: int = 0,
        device: Optional[str] = None,
        source_kind: Optional[str] = None,
        sort: str = "asc",
    ) -> tuple[list, int]:
        """Query audio transcriptions within a time range with pagination."""
        transcriptions: list = []
        total = 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Build WHERE clause with optional device filter
                where = "at.timestamp >= ? AND at.timestamp <= ?"
                params: list = [start_time, end_time]
                if device:
                    where += " AND ac.device_name = ?"
                    params.append(device)
                if source_kind:
                    where += " AND COALESCE(ac.source_kind, 'unknown') = ?"
                    params.append(source_kind)
                sort_order = "DESC" if str(sort).lower() == "desc" else "ASC"

                cursor.execute(
                    f"""SELECT COUNT(*) FROM audio_transcriptions at
                        JOIN audio_chunks ac ON at.audio_chunk_id = ac.id
                        WHERE {where}""",
                    params,
                )
                total = cursor.fetchone()[0]
                cursor.execute(
                    f"""SELECT at.id, at.audio_chunk_id, at.offset_index, at.timestamp,
                              at.transcription, at.transcription_engine, at.speaker_id,
                              at.start_time, at.end_time, at.text_length,
                              ac.device_name, ac.file_path AS chunk_path,
                              ac.source_kind, ac.is_input, ac.created_at AS chunk_created_at
                       FROM audio_transcriptions at
                       JOIN audio_chunks ac ON at.audio_chunk_id = ac.id
                       WHERE {where}
                       ORDER BY at.timestamp {sort_order}
                       LIMIT ? OFFSET ?""",
                    params + [limit, offset],
                )
                for row in cursor.fetchall():
                    transcriptions.append(dict(row))
        except sqlite3.Error as e:
            logger.error(f"Failed to query audio transcriptions by time range: {e}")
        return transcriptions, total

    # =========================================================================
    # Phase 2: Audio Retention Methods
    # =========================================================================

    def get_expired_audio_chunks(self) -> list:
        """Get audio chunks that have expired and are completed."""
        results: list = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM audio_chunks WHERE expires_at < datetime('now') AND status='COMPLETED'"
                )
                results = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get expired audio chunks: {e}")
        return results

    def delete_audio_chunk_cascade(self, chunk_id: int) -> int:
        """Delete an audio chunk and all associated data. Returns number of transcriptions deleted."""
        transcriptions_deleted = 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("PRAGMA foreign_keys=ON")
                cursor = conn.cursor()
                # Delete FTS entries (not covered by CASCADE)
                cursor.execute(
                    "DELETE FROM audio_transcriptions_fts WHERE audio_chunk_id = ?",
                    (chunk_id,),
                )
                # Count transcriptions before cascade delete
                cursor.execute(
                    "SELECT COUNT(*) FROM audio_transcriptions WHERE audio_chunk_id=?",
                    (chunk_id,),
                )
                transcriptions_deleted = cursor.fetchone()[0]
                # CASCADE handles audio_transcriptions
                cursor.execute("DELETE FROM audio_chunks WHERE id=?", (chunk_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to cascade delete audio chunk {chunk_id}: {e}")
        return transcriptions_deleted

    # =========================================================================
    # Phase 2.5: Dashboard Pagination & Statistics Methods
    # =========================================================================

    def get_video_chunks_paginated(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        monitor_id: Optional[str] = None,
    ) -> Tuple[list, int]:
        """Get video chunks with pagination and optional filters. Returns (chunks, total)."""
        chunks: list = []
        total = 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if not self._table_exists(conn, "video_chunks"):
                    return chunks, total
                where_clauses: list = []
                params: list = []
                if status:
                    where_clauses.append("status = ?")
                    params.append(status.upper())
                if monitor_id:
                    where_clauses.append("monitor_id = ?")
                    params.append(monitor_id)
                where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
                cursor.execute(f"SELECT COUNT(*) FROM video_chunks{where_sql}", params)
                total = cursor.fetchone()[0]
                cursor.execute(
                    f"SELECT * FROM video_chunks{where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    params + [limit, offset],
                )
                chunks = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get paginated video chunks: {e}")
        return chunks, total

    def get_frames_paginated(
        self,
        limit: int = 50,
        offset: int = 0,
        chunk_id: Optional[int] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Tuple[list, int]:
        """Get frames with pagination and optional filters. Returns (frames, total) with OCR snippet."""
        frames: list = []
        total = 0
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if not self._table_exists(conn, "frames"):
                    return frames, total
                where_clauses: list = []
                params: list = []
                if chunk_id is not None:
                    where_clauses.append("f.video_chunk_id = ?")
                    params.append(chunk_id)
                if app_name:
                    where_clauses.append("f.app_name LIKE ?")
                    params.append(f"%{app_name}%")
                if window_name:
                    where_clauses.append("f.window_name LIKE ?")
                    params.append(f"%{window_name}%")
                if start_time is not None:
                    where_clauses.append("f.timestamp >= ?")
                    params.append(start_time)
                if end_time is not None:
                    where_clauses.append("f.timestamp <= ?")
                    params.append(end_time)
                where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
                cursor.execute(f"SELECT COUNT(*) FROM frames f{where_sql}", params)
                total = cursor.fetchone()[0]
                cursor.execute(
                    f"""SELECT f.id AS frame_id, f.video_chunk_id, f.offset_index, f.timestamp,
                              f.app_name, f.window_name, f.focused, f.browser_url,
                              SUBSTR(COALESCE(ot.text, ''), 1, 200) AS ocr_snippet
                       FROM frames f
                       LEFT JOIN ocr_text ot ON f.id = ot.frame_id
                       {where_sql}
                       ORDER BY f.timestamp DESC
                       LIMIT ? OFFSET ?""",
                    params + [limit, offset],
                )
                for row in cursor.fetchall():
                    d = dict(row)
                    d["frame_url"] = f"/api/v1/frames/{d['frame_id']}"
                    raw_focused = d.get("focused")
                    d["focused"] = bool(raw_focused) if raw_focused is not None else None
                    raw_url = d.get("browser_url")
                    d["browser_url"] = raw_url if raw_url else None
                    frames.append(d)
        except sqlite3.Error as e:
            logger.error(f"Failed to get paginated frames: {e}")
        return frames, total

    def get_video_stats(self) -> dict:
        """Get aggregated video statistics."""
        stats: dict = {
            "total_chunks": 0,
            "total_frames": 0,
            "total_duration_seconds": 0.0,
            "storage_bytes": 0,
            "status_counts": {},
        }
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                if not self._table_exists(conn, "video_chunks"):
                    return stats
                cursor.execute("SELECT COUNT(*) FROM video_chunks")
                stats["total_chunks"] = cursor.fetchone()[0]
                if self._table_exists(conn, "frames"):
                    cursor.execute("SELECT COUNT(*) FROM frames")
                    stats["total_frames"] = cursor.fetchone()[0]
                cursor.execute("SELECT status, COUNT(*) FROM video_chunks GROUP BY status")
                stats["status_counts"] = {str(s): int(c) for s, c in cursor.fetchall()}
                cursor.execute(
                    "SELECT COALESCE(SUM(end_time - start_time), 0) "
                    "FROM video_chunks WHERE start_time IS NOT NULL AND end_time IS NOT NULL"
                )
                stats["total_duration_seconds"] = round(cursor.fetchone()[0], 1)
                cursor.execute("SELECT file_path FROM video_chunks")
                total_bytes = 0
                for (fp,) in cursor.fetchall():
                    try:
                        p = Path(fp)
                        if p.exists():
                            total_bytes += p.stat().st_size
                    except (OSError, ValueError):
                        pass
                stats["storage_bytes"] = total_bytes
        except sqlite3.Error as e:
            logger.error(f"Failed to get video stats: {e}")
        return stats

    def get_audio_stats(self) -> dict:
        """Get aggregated audio statistics."""
        stats: dict = {
            "total_chunks": 0,
            "total_transcriptions": 0,
            "total_duration_seconds": 0.0,
            "storage_bytes": 0,
            "status_counts": {},
            "device_counts": {},
            "source_counts": {},
        }
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                if not self._table_exists(conn, "audio_chunks"):
                    return stats
                cursor.execute("SELECT COUNT(*) FROM audio_chunks")
                stats["total_chunks"] = cursor.fetchone()[0]
                if self._table_exists(conn, "audio_transcriptions"):
                    cursor.execute("SELECT COUNT(*) FROM audio_transcriptions")
                    stats["total_transcriptions"] = cursor.fetchone()[0]
                try:
                    cursor.execute(
                        "SELECT COALESCE(SUM(CASE WHEN end_time >= start_time THEN end_time - start_time ELSE 0 END), 0) "
                        "FROM audio_chunks WHERE start_time IS NOT NULL AND end_time IS NOT NULL"
                    )
                    stats["total_duration_seconds"] = round(float(cursor.fetchone()[0] or 0.0), 1)
                except sqlite3.Error:
                    # Older schemas may not have timing columns yet.
                    stats["total_duration_seconds"] = 0.0
                cursor.execute("SELECT status, COUNT(*) FROM audio_chunks GROUP BY status")
                stats["status_counts"] = {str(s): int(c) for s, c in cursor.fetchall()}
                cursor.execute("SELECT device_name, COUNT(*) FROM audio_chunks GROUP BY device_name")
                stats["device_counts"] = {str(d or "unknown"): int(c) for d, c in cursor.fetchall()}
                try:
                    cursor.execute(
                        "SELECT COALESCE(source_kind, 'unknown'), COUNT(*) FROM audio_chunks GROUP BY source_kind"
                    )
                    stats["source_counts"] = {str(s or "unknown"): int(c) for s, c in cursor.fetchall()}
                except sqlite3.Error:
                    # Older schemas may not have source_kind yet.
                    stats["source_counts"] = {}
                cursor.execute("SELECT file_path FROM audio_chunks")
                total_bytes = 0
                for (fp,) in cursor.fetchall():
                    try:
                        p = Path(fp)
                        if p.exists():
                            total_bytes += p.stat().st_size
                    except (OSError, ValueError):
                        pass
                stats["storage_bytes"] = total_bytes
        except sqlite3.Error as e:
            logger.error(f"Failed to get audio stats: {e}")
        return stats
