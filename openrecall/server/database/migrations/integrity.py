"""Data integrity verification for MyRecall migrations.

Provides SHA256 checksum computation and verification for the entries
table to ensure zero data loss during migration/rollback operations.
"""

import hashlib
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def compute_entries_checksum(conn: sqlite3.Connection) -> str:
    """Compute SHA256 checksum of all entries rows.

    Serializes each row as 'id|timestamp|app|title|text|status' and
    computes a cumulative SHA256 hash.

    Args:
        conn: SQLite connection to the database.

    Returns:
        Hex-encoded SHA256 checksum string.
    """
    hasher = hashlib.sha256()

    cursor = conn.execute(
        "SELECT id, timestamp, app, title, text, status "
        "FROM entries ORDER BY id"
    )

    for row in cursor:
        # Serialize each row consistently
        row_str = "|".join(str(v) if v is not None else "" for v in row)
        hasher.update(row_str.encode("utf-8"))

    return hasher.hexdigest()


def save_checksum(checksum: str, path: Path) -> None:
    """Save a checksum to a file.

    Args:
        checksum: Hex-encoded checksum string.
        path: File path to write the checksum to.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(checksum, encoding="utf-8")
    logger.debug(f"Checksum saved to {path}: {checksum[:16]}...")


def verify_checksum(conn: sqlite3.Connection, path: Path) -> bool:
    """Verify current entries checksum against a saved checksum.

    Args:
        conn: SQLite connection to the database.
        path: File path containing the saved checksum.

    Returns:
        True if checksums match, False otherwise.
    """
    if not path.exists():
        logger.error(f"Checksum file not found: {path}")
        return False

    saved = path.read_text(encoding="utf-8").strip()
    current = compute_entries_checksum(conn)

    match = saved == current
    if not match:
        logger.error(
            f"Checksum mismatch! Saved: {saved[:16]}... "
            f"Current: {current[:16]}..."
        )
    else:
        logger.debug(f"Checksum verified: {current[:16]}...")

    return match
