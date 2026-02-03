import logging
import sqlite3
import numpy as np
from typing import List, Tuple, Optional, Any
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

    def get_recent_memories(self, limit: int = 200) -> List[dict]:
        """Retrieves recent memories for API."""
        memories: List[dict] = []
        normalized_limit = max(1, min(int(limit) if limit else 200, 1000))

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, app, title, text, description, timestamp, status FROM entries "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (normalized_limit,),
                )
                for row in cursor.fetchall():
                    ts = row["timestamp"]
                    memories.append(
                        {
                            "id": row["id"],
                            "timestamp": ts,
                            "app": row["app"],
                            "title": row["title"],
                            "text": row["text"],
                            "description": row["description"],
                            "status": row["status"] if "status" in row.keys() else "COMPLETED",
                            "filename": f"{ts}.png",
                            "app_name": row["app"],
                            "window_title": row["title"],
                        }
                    )
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching recent memories: {e}")
        return memories

    def get_memories_since(self, timestamp: float) -> List[dict]:
        """Retrieves entries with timestamp > timestamp."""
        memories: List[dict] = []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, app, title, text, description, timestamp, status FROM entries "
                    "WHERE timestamp > ? ORDER BY timestamp DESC",
                    (timestamp,),
                )
                for row in cursor.fetchall():
                    ts = row["timestamp"]
                    memories.append(
                        {
                            "id": row["id"],
                            "timestamp": ts,
                            "app": row["app"],
                            "title": row["title"],
                            "text": row["text"],
                            "description": row["description"],
                            "status": row["status"] if "status" in row.keys() else "COMPLETED",
                            "filename": f"{ts}.png",
                            "app_name": row["app"],
                            "window_title": row["title"],
                        }
                    )
        except sqlite3.Error as e:
            logger.error(f"Database error while fetching memories since time: {e}")
        return memories
