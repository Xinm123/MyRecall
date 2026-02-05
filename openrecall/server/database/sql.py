import logging
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np

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
        self.fts_path = self.get_fts_path(None)
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
        self._init_fts_db(self.fts_path)

        self._migrate_to_m0()

    def _is_m0_schema(self) -> bool:
        """Check whether the entries table is already on M0 schema."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute("PRAGMA table_info(entries)")
                columns = {row[1] for row in cursor.fetchall()}
            return "device_id" in columns
        except sqlite3.Error as e:
            logger.error(f"Failed to inspect schema for M0 migration: {e}")
            return False

    def _migrate_to_m0(self) -> None:
        """Migrate legacy entries schema to M0 schema if needed."""
        if self._is_m0_schema():
            return

        db_path = Path(self.db_path)
        if db_path.exists():
            backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path(f"{db_path}.bak_m0_{backup_suffix}")
            shutil.copy2(db_path, backup_path)

        legacy_device_id = settings.legacy_device_id or "legacy"

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    """CREATE TABLE entries_m0 (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           app TEXT,
                           title TEXT,
                           text TEXT,
                           timestamp INTEGER,
                           embedding BLOB,
                           description TEXT,
                           status TEXT DEFAULT 'COMPLETED',
                           device_id TEXT NOT NULL,
                           client_ts INTEGER NOT NULL,
                           client_tz TEXT,
                           client_seq INTEGER,
                           image_hash TEXT,
                           server_received_at INTEGER NOT NULL,
                           image_relpath TEXT NOT NULL,
                           UNIQUE(device_id, client_ts)
                       )"""
                )
                cursor.execute(
                    """INSERT INTO entries_m0 (
                           app,
                           title,
                           text,
                           timestamp,
                           embedding,
                           description,
                           status,
                           device_id,
                           client_ts,
                           client_tz,
                           client_seq,
                           image_hash,
                           server_received_at,
                           image_relpath
                       )
                       SELECT app,
                              title,
                              text,
                              timestamp,
                              embedding,
                              description,
                              status,
                              ?,
                              timestamp * 1000,
                              NULL,
                              NULL,
                              NULL,
                              timestamp * 1000,
                              CAST(timestamp AS TEXT) || '.png'
                       FROM entries""",
                    (legacy_device_id,),
                )
                cursor.execute("DROP TABLE entries")
                cursor.execute("ALTER TABLE entries_m0 RENAME TO entries")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entries_device_client_ts "
                    "ON entries(device_id, client_ts)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entries_status_received "
                    "ON entries(status, server_received_at)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)"
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to migrate entries schema to M0: {e}")
            raise

    # =========================================================================
    # FTS Methods
    # =========================================================================

    @classmethod
    def get_fts_path(cls, device_id: str | None) -> Path:
        if device_id in {None, "legacy", settings.legacy_device_id}:
            return settings.fts_path
        return settings.server_data_dir / "fts" / f"{device_id}.db"

    def _init_fts_db(self, fts_path: Path) -> None:
        try:
            fts_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(fts_path)) as conn:
                conn.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts
                       USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)"""
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize FTS database: {e}")
            raise

    def add_document(
        self,
        snapshot_id: str,
        ocr_text: str,
        caption: str,
        keywords: List[str],
        device_id: str | None = None,
    ) -> None:
        """Add a document to the FTS index."""
        keywords_str = " ".join(keywords)
        fts_path = self.get_fts_path(device_id)
        try:
            self._init_fts_db(fts_path)
            with sqlite3.connect(str(fts_path)) as conn:
                conn.execute(
                    "INSERT INTO ocr_fts (snapshot_id, ocr_text, caption, keywords) VALUES (?, ?, ?, ?)",
                    (str(snapshot_id), ocr_text, caption, keywords_str),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to add document to FTS: {e}")

    def search(
        self, query: str, limit: int = 10, device_id: str | None = None
    ) -> List[Tuple[str, float]]:
        """Search for documents matching the query. Returns list of (snapshot_id, bm25_score)."""
        fts_path = self.get_fts_path(device_id)
        try:
            self._init_fts_db(fts_path)
            with sqlite3.connect(str(fts_path)) as conn:
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

        device_id = row["device_id"] if "device_id" in row.keys() else None
        client_ts = row["client_ts"] if "client_ts" in row.keys() else None
        client_tz = row["client_tz"] if "client_tz" in row.keys() else None
        client_seq = row["client_seq"] if "client_seq" in row.keys() else None
        image_hash = row["image_hash"] if "image_hash" in row.keys() else None
        server_received_at = (
            row["server_received_at"] if "server_received_at" in row.keys() else None
        )
        image_relpath = row["image_relpath"] if "image_relpath" in row.keys() else None

        return RecallEntry(
            id=row["id"],
            app=row["app"],
            title=row["title"],
            text=row["text"],
            description=row["description"],
            timestamp=row["timestamp"],
            embedding=row["embedding"],
            status=status,
            device_id=device_id,
            client_ts=client_ts,
            client_tz=client_tz,
            client_seq=client_seq,
            image_hash=image_hash,
            server_received_at=server_received_at,
            image_relpath=image_relpath,
        )

    def insert_pending_entry(
        self, timestamp: int, app: str, title: str, image_path: str
    ) -> Optional[int]:
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
                    logger.info(
                        f"Fast ingestion: Inserted PENDING entry (id={last_row_id}, ts={timestamp})"
                    )
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
                    cursor.execute(
                        "SELECT COUNT(*) FROM entries WHERE status='PENDING'"
                    )
                    count = cursor.fetchone()[0]
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM entries WHERE status='PENDING'")
                count = cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Database error while counting pending tasks: {e}")
        return count

    def get_next_task(
        self, conn: sqlite3.Connection, lifo_mode: bool = False
    ) -> Optional[RecallEntry]:
        """Get the next pending task to process."""
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            order = "DESC" if lifo_mode else "ASC"
            cursor.execute(
                f"SELECT id, app, title, text, description, timestamp, embedding, status, "
                f"device_id, client_ts, server_received_at, image_relpath "
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
            cursor.execute(
                "UPDATE entries SET status='PROCESSING' WHERE id=?", (task_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(
                f"Database error while marking task {task_id} as processing: {e}"
            )
            return False

    def mark_task_cancelled_if_processing(
        self, conn: sqlite3.Connection, task_id: int
    ) -> bool:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE entries SET status='CANCELLED' WHERE id=? AND status='PROCESSING'",
                (task_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error while cancelling task {task_id}: {e}")
            return False

    def mark_task_completed(
        self,
        conn: sqlite3.Connection,
        task_id: int,
        text: str,
        description: Optional[str],
        embedding: np.ndarray[Any, Any],
    ) -> bool:
        """Mark a task as completed with processing results."""
        try:
            embedding_bytes = embedding.astype(np.float32).tobytes()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE entries SET text=?, description=?, embedding=?, status='COMPLETED' "
                "WHERE id=? AND status IN ('PROCESSING', 'PENDING')",
                (text, description, embedding_bytes, task_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(
                f"Database error while marking task {task_id} as completed: {e}"
            )
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
                    cursor.execute(
                        "UPDATE entries SET status='PENDING' WHERE status='PROCESSING'"
                    )
                    count = cursor.rowcount
                    conn.commit()
            else:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE entries SET status='PENDING' WHERE status='PROCESSING'"
                )
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
                    cursor.execute(
                        "UPDATE entries SET status='CANCELLED' WHERE status='PROCESSING'"
                    )
                    count = cursor.rowcount
                    conn.commit()
            else:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE entries SET status='CANCELLED' WHERE status='PROCESSING'"
                )
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
                    "SELECT id, app, title, text, description, timestamp, embedding, status, image_relpath FROM entries "
                    "ORDER BY timestamp DESC"
                )
                entries = [self._row_to_entry(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching all entries with status: {e}")
        return entries

    def get_timestamps(self) -> List[int]:
        """Retrieves all timestamps from the database."""
        timestamps: List[int] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp FROM entries ORDER BY timestamp DESC")
                results = cursor.fetchall()
                timestamps = [result[0] for result in results]
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching timestamps: {e}")
        return timestamps

    def get_timeline_data(self) -> list[dict[str, object]]:
        """Retrieves timestamp and image_relpath for timeline view."""
        entries: list[dict[str, object]] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT timestamp, image_relpath FROM entries ORDER BY timestamp DESC"
                )
                for row in cursor.fetchall():
                    ts = row["timestamp"]
                    image_relpath = row["image_relpath"]
                    entries.append(
                        {
                            "timestamp": ts,
                            "filename": image_relpath if image_relpath else f"{ts}.png",
                        }
                    )
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching timeline data: {e}")
        return entries

    def get_recent_memories(self, limit: int = 200) -> list[dict[str, object]]:
        """Retrieves recent memories for API."""
        memories: list[dict[str, object]] = []
        normalized_limit = max(1, min(int(limit) if limit else 200, 1000))

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, app, title, text, description, timestamp, status, image_relpath FROM entries "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (normalized_limit,),
                )
                for row in cursor.fetchall():
                    ts = row["timestamp"]
                    image_relpath = (
                        row["image_relpath"] if "image_relpath" in row.keys() else None
                    )
                    memories.append(
                        {
                            "id": row["id"],
                            "timestamp": ts,
                            "app": row["app"],
                            "title": row["title"],
                            "text": row["text"],
                            "description": row["description"],
                            "status": row["status"]
                            if "status" in row.keys()
                            else "COMPLETED",
                            "filename": image_relpath if image_relpath else f"{ts}.png",
                            "app_name": row["app"],
                            "window_title": row["title"],
                        }
                    )
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching recent memories: {e}")
        return memories

    def get_memories_since(self, timestamp: float) -> list[dict[str, object]]:
        """Retrieves entries with timestamp > timestamp."""
        memories: list[dict[str, object]] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, app, title, text, description, timestamp, status, image_relpath FROM entries "
                    "WHERE timestamp > ? ORDER BY timestamp DESC",
                    (timestamp,),
                )
                for row in cursor.fetchall():
                    ts = row["timestamp"]
                    image_relpath = (
                        row["image_relpath"] if "image_relpath" in row.keys() else None
                    )
                    memories.append(
                        {
                            "id": row["id"],
                            "timestamp": ts,
                            "app": row["app"],
                            "title": row["title"],
                            "text": row["text"],
                            "description": row["description"],
                            "status": row["status"]
                            if "status" in row.keys()
                            else "COMPLETED",
                            "filename": image_relpath if image_relpath else f"{ts}.png",
                            "app_name": row["app"],
                            "window_title": row["title"],
                        }
                    )
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching memories since time: {e}")
        return memories

    def get_entry_by_device_client_ts(
        self, device_id: str, client_ts: int
    ) -> dict[str, object] | None:
        """Get entry by device_id and client_ts for idempotency check."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, device_id, client_ts, image_hash, status, "
                    "server_received_at, image_relpath "
                    "FROM entries WHERE device_id = ? AND client_ts = ?",
                    (device_id, client_ts),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "device_id": row["device_id"],
                        "client_ts": row["client_ts"],
                        "image_hash": row["image_hash"],
                        "status": row["status"],
                        "server_received_at": row["server_received_at"],
                        "image_relpath": row["image_relpath"],
                    }
        except sqlite3.Error as e:
            logger.error(
                f"Database error while checking idempotency (device={device_id}, client_ts={client_ts}): {e}"
            )
        return None

    def insert_pending_entry_v1(
        self,
        device_id: str,
        client_ts: int,
        client_tz: str | None,
        client_seq: int | None,
        image_hash: str,
        app: str,
        title: str,
        server_received_at: int,
        image_relpath: str,
        timestamp: int | None = None,
    ) -> int:
        """Insert a PENDING entry with M0 contract fields."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO entries (
                        device_id, client_ts, client_tz, client_seq, image_hash,
                        app, title, image_relpath, server_received_at, timestamp, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')""",
                    (
                        device_id,
                        client_ts,
                        client_tz,
                        client_seq,
                        image_hash,
                        app,
                        title,
                        image_relpath,
                        server_received_at,
                        timestamp,
                    ),
                )
                conn.commit()
                last_row_id = cursor.lastrowid
                if last_row_id is None:
                    raise sqlite3.Error("Failed to insert pending M0 entry")
                logger.info(
                    f"M0 ingestion: Inserted PENDING entry (id={last_row_id}, device={device_id}, client_ts={client_ts})"
                )
                return int(last_row_id)
        except sqlite3.Error as e:
            logger.error(f"Database error during M0 ingestion: {e}")
            raise
