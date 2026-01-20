import logging
import sqlite3
import numpy as np
from typing import List, Optional

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)
from openrecall.shared.models import RecallEntry


def create_db() -> None:
    """
    Creates the SQLite database and the 'entries' table if they don't exist.

    The table schema includes columns for an auto-incrementing ID, application name,
    window title, extracted text, timestamp, and text embedding.
    """
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS entries (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       app TEXT,
                       title TEXT,
                       text TEXT,
                       timestamp INTEGER UNIQUE,
                       embedding BLOB
                   )"""
            )
            # Add index on timestamp for faster lookups
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)"
            )
            conn.commit()
            # Run migrations for schema updates
            _migrate_db(conn)
    except sqlite3.Error as e:
        print(f"Database error during table creation: {e}")


def _migrate_db(conn: sqlite3.Connection) -> None:
    """Run database migrations to update schema.
    
    Checks for missing columns and adds them if needed.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(entries)")
    columns = {row[1] for row in cursor.fetchall()}
    
    # Migration: Add description column for MLLM integration (Phase 6)
    if "description" not in columns:
        cursor.execute("ALTER TABLE entries ADD COLUMN description TEXT")
        conn.commit()
        logger.info("Database schema updated: added 'description' column.")
    
    # Migration: Add status column for async processing (Phase 6.4)
    if "status" not in columns:
        cursor.execute("ALTER TABLE entries ADD COLUMN status TEXT DEFAULT 'COMPLETED'")
        conn.commit()
        logger.info("Database schema updated: added 'status' column.")


def _row_to_entry(row: sqlite3.Row) -> RecallEntry:
    """Convert a database row to RecallEntry (embedding auto-deserialized by Pydantic)."""
    # Handle status field (may not exist in old rows)
    try:
        status = row["status"]
    except (KeyError, IndexError):
        status = "COMPLETED"  # Default for old rows without status
    
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


def get_all_entries() -> List[RecallEntry]:
    """Retrieves all COMPLETED entries from the database.
    
    Only returns entries with status='COMPLETED' (fully processed).
    PENDING entries are excluded from search results.

    Returns:
        List[RecallEntry]: A list of all completed entries as RecallEntry objects.
                           Returns an empty list if the table is empty or an error occurs.
    """
    entries: List[RecallEntry] = []
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, app, title, text, description, timestamp, embedding, status FROM entries "
                "WHERE status='COMPLETED' ORDER BY timestamp DESC"
            )
            entries = [_row_to_entry(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Database error while fetching all entries: {e}")
    return entries


def get_all_entries_with_status() -> List[RecallEntry]:
    """Retrieves ALL entries from the database regardless of status.
    
    Returns entries in all states: PENDING, PROCESSING, COMPLETED, FAILED.
    Useful for displaying real-time processing status in the UI.

    Returns:
        List[RecallEntry]: A list of all entries as RecallEntry objects.
                           Returns an empty list if the table is empty or an error occurs.
    """
    entries: List[RecallEntry] = []
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, app, title, text, description, timestamp, embedding, status FROM entries "
                "ORDER BY timestamp DESC"
            )
            entries = [_row_to_entry(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Database error while fetching all entries with status: {e}")
    return entries


def get_timestamps() -> List[int]:
    """
    Retrieves all timestamps from the database, ordered descending.

    Returns:
        List[int]: A list of all timestamps.
                   Returns an empty list if the table is empty or an error occurs.
    """
    timestamps: List[int] = []
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
            cursor = conn.cursor()
            # Use the index for potentially faster retrieval
            cursor.execute("SELECT timestamp FROM entries ORDER BY timestamp DESC")
            results = cursor.fetchall()
            timestamps = [result[0] for result in results]
    except sqlite3.Error as e:
        print(f"Database error while fetching timestamps: {e}")
    return timestamps


def insert_entry(
    text: str,
    timestamp: int,
    embedding: np.ndarray,
    app: str,
    title: str,
    description: str | None = None,
) -> Optional[int]:
    """
    Inserts a new entry into the database.

    Args:
        text (str): The extracted text content.
        timestamp (int): The Unix timestamp of the screenshot.
        embedding (np.ndarray): The embedding vector for the text.
        app (str): The name of the active application.
        title (str): The title of the active window.
        description (str | None): AI-generated semantic description of the image.

    Returns:
        Optional[int]: The ID of the newly inserted row, or None if insertion fails.
                       Prints an error message to stderr on failure.
    """
    embedding_bytes: bytes = embedding.astype(
        np.float32
    ).tobytes()  # Ensure consistent dtype
    last_row_id: Optional[int] = None
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO entries (text, timestamp, embedding, app, title, description)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(timestamp) DO NOTHING""",  # Avoid duplicates based on timestamp
                (text, timestamp, embedding_bytes, app, title, description),
            )
            conn.commit()
            if cursor.rowcount > 0:  # Check if insert actually happened
                last_row_id = cursor.lastrowid
            # else:
            # Optionally log that a duplicate timestamp was encountered
            # print(f"Skipped inserting entry with duplicate timestamp: {timestamp}")

    except sqlite3.Error as e:
        # More specific error handling can be added (e.g., IntegrityError for UNIQUE constraint)
        print(f"Database error during insertion: {e}")
    return last_row_id


def insert_pending_entry(
    timestamp: int,
    app: str,
    title: str,
    image_path: str,
) -> Optional[int]:
    """Insert a PENDING entry for async processing.
    
    This is the fast ingestion path - no OCR, AI, or embedding computation.
    The worker will process it later.
    
    Args:
        timestamp: Unix timestamp of the screenshot.
        app: Name of the active application.
        title: Title of the active window.
        image_path: Path to saved screenshot image.
        
    Returns:
        ID of the newly inserted row, or None if insertion fails.
    """
    last_row_id: Optional[int] = None
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
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


def get_entries_by_time_range(start_time: int, end_time: int) -> List[RecallEntry]:
    """Retrieves COMPLETED entries within a specified time range.
    
    Only returns entries with status='COMPLETED' (fully processed).
    PENDING entries are excluded from search results.

    Args:
        start_time: Unix timestamp for range start.
        end_time: Unix timestamp for range end.

    Returns:
        List[RecallEntry]: Completed entries within the time range, ordered by timestamp DESC.
    """
    entries: List[RecallEntry] = []
    try:
        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, app, title, text, description, timestamp, embedding, status FROM entries "
                "WHERE timestamp BETWEEN ? AND ? AND status='COMPLETED' ORDER BY timestamp DESC",
                (start_time, end_time),
            )
            entries = [_row_to_entry(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Database error while fetching entries by time range: {e}")
    return entries


# ============================================================================
# Async Infrastructure Helper Methods (Phase 6.4)
# ============================================================================

def get_pending_count(conn: Optional[sqlite3.Connection] = None) -> int:
    """Count the number of pending tasks.
    
    Args:
        conn: Optional database connection. If None, creates a new one.
        
    Returns:
        Number of entries with status='PENDING'.
    """
    count = 0
    try:
        if conn is None:
            with sqlite3.connect(str(settings.db_path)) as conn:
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


def get_next_task(conn: sqlite3.Connection, lifo_mode: bool = False) -> Optional[RecallEntry]:
    """Get the next pending task to process.
    
    Args:
        conn: Database connection.
        lifo_mode: If True, get newest task (LIFO). If False, get oldest (FIFO).
        
    Returns:
        RecallEntry with status='PENDING', or None if no pending tasks.
    """
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        order = "DESC" if lifo_mode else "ASC"
        cursor.execute(
            f"SELECT id, app, title, text, description, timestamp, embedding, status "
            f"FROM entries WHERE status='PENDING' ORDER BY timestamp {order} LIMIT 1"
        )
        row = cursor.fetchone()
        if row:
            return _row_to_entry(row)
    except sqlite3.Error as e:
        logger.error(f"Database error while fetching next task: {e}")
    return None


def reset_stuck_tasks(conn: Optional[sqlite3.Connection] = None) -> int:
    """Reset tasks stuck in PROCESSING state back to PENDING.
    
    This is used for crash recovery at startup.
    
    Args:
        conn: Optional database connection. If None, creates a new one.
        
    Returns:
        Number of tasks reset.
    """
    count = 0
    try:
        if conn is None:
            with sqlite3.connect(str(settings.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE entries SET status='PENDING' WHERE status='PROCESSING'")
                count = cursor.rowcount
                conn.commit()
                if count > 0:
                    logger.info(f"Reset {count} stuck tasks from PROCESSING to PENDING")
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


def mark_task_processing(conn: sqlite3.Connection, task_id: int) -> bool:
    """Mark a task as currently being processed.
    
    Args:
        conn: Database connection.
        task_id: Entry ID to mark as processing.
        
    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE entries SET status='PROCESSING' WHERE id=?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Database error while marking task {task_id} as processing: {e}")
        return False


def mark_task_completed(
    conn: sqlite3.Connection,
    task_id: int,
    text: str,
    description: Optional[str],
    embedding: np.ndarray
) -> bool:
    """Mark a task as completed with processing results.
    
    Args:
        conn: Database connection.
        task_id: Entry ID to update.
        text: OCR extracted text.
        description: AI-generated description.
        embedding: Embedding vector.
        
    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        embedding_bytes = embedding.astype(np.float32).tobytes()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE entries SET text=?, description=?, embedding=?, status='COMPLETED' WHERE id=?",
            (text, description, embedding_bytes, task_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Database error while marking task {task_id} as completed: {e}")
        return False


def mark_task_failed(conn: sqlite3.Connection, task_id: int) -> bool:
    """Mark a task as failed.
    
    Args:
        conn: Database connection.
        task_id: Entry ID to mark as failed.
        
    Returns:
        True if update succeeded, False otherwise.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE entries SET status='FAILED' WHERE id=?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Database error while marking task {task_id} as failed: {e}")
        return False
