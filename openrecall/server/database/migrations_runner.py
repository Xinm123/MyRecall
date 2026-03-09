"""Migration runner for v3 Edge database."""

import re
import sqlite3
from pathlib import Path
from typing import Set


_SELF_RECORD_PATTERN = re.compile(
    r"\bINSERT\s+INTO\s+schema_migrations\b", re.IGNORECASE
)


def verify_schema_integrity(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ? LIMIT 1",
        ("20260227000001",),
    ).fetchone()
    if row is None:
        return

    required_table_names = {
        "frames",
        "ocr_text",
        "chat_messages",
        "accessibility",
    }
    existing_tables = {
        result[0]
        for result in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('frames', 'ocr_text', 'chat_messages', 'accessibility')"
        )
    }
    missing_tables = sorted(required_table_names - existing_tables)

    required_index_names = {
        "idx_frames_timestamp",
        "idx_frames_status",
        "idx_chat_session",
    }
    existing_indexes = {
        result[0]
        for result in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_frames_timestamp', 'idx_frames_status', 'idx_chat_session')"
        )
    }
    missing_indexes = sorted(required_index_names - existing_indexes)

    if missing_tables or missing_indexes:
        parts: list[str] = []
        if missing_tables:
            parts.append(f"missing tables: {', '.join(missing_tables)}")
        if missing_indexes:
            parts.append(f"missing indexes: {', '.join(missing_indexes)}")
        raise sqlite3.IntegrityError(
            "schema integrity check failed for version 20260227000001: "
            + "; ".join(parts)
        )


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    """Run pending migrations.

    Args:
        conn: SQLite connection
        migrations_dir: Directory containing migration SQL files

    Raises:
        sqlite3.Error: If migration fails
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )

    applied: Set[str] = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations")
    }

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = sql_file.stem.split("_")[0]
        if version not in applied:
            script = sql_file.read_text(encoding="utf-8")
            if _SELF_RECORD_PATTERN.search(script):
                raise ValueError(
                    f"Migration {sql_file.name} must not write schema_migrations directly"
                )

            try:
                conn.executescript("\n".join(["BEGIN IMMEDIATE;", script]))
                conn.execute(
                    "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
                    (version, sql_file.stem),
                )
                conn.execute("COMMIT")
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.rollback()
                raise

            applied.add(version)

    verify_schema_integrity(conn)
    conn.commit()
