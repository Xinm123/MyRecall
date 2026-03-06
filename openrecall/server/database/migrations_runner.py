"""Migration runner for v3 Edge database."""

import sqlite3
from pathlib import Path
from typing import Set


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
            conn.executescript(sql_file.read_text())
            conn.execute(
                "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
                (version, sql_file.stem),
            )

    conn.commit()
