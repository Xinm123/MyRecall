"""Migration runner for MyRecall v3 database schema evolution.

Applies SQL migration files in version order with idempotency,
timing, and memory measurement.
"""

import logging
import re
import sqlite3
import time
import tracemalloc
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


@dataclass
class MigrationResult:
    """Result of a migration run."""
    success: bool
    elapsed_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    tables_created: List[str] = field(default_factory=list)
    version: int = 0
    error: Optional[str] = None


class MigrationRunner:
    """Applies SQL migration files to a SQLite database.

    Migrations are .sql files in the migrations directory named
    v3_NNN_description.sql where NNN is the version number.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _ensure_schema_version_table(self, conn: sqlite3.Connection) -> None:
        """Create schema_version table if it doesn't exist."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                description TEXT
            )"""
        )
        conn.commit()

    def _get_applied_versions(self, conn: sqlite3.Connection) -> set:
        """Get set of already-applied migration versions."""
        cursor = conn.execute("SELECT version FROM schema_version")
        return {row[0] for row in cursor.fetchall()}

    def _discover_migrations(self) -> List[tuple]:
        """Discover .sql migration files and parse their version numbers.

        Returns:
            List of (version, path, description) sorted by version.
        """
        migrations = []
        for sql_file in sorted(MIGRATIONS_DIR.glob("v3_*.sql")):
            match = re.match(r"v3_(\d+)_(.+)\.sql", sql_file.name)
            if match:
                version = int(match.group(1))
                description = match.group(2).replace("_", " ")
                migrations.append((version, sql_file, description))
        return sorted(migrations, key=lambda x: x[0])

    def _apply_sql_file(self, conn: sqlite3.Connection, sql_path: Path) -> List[str]:
        """Apply a SQL migration file with idempotency for ALTER TABLE.

        Returns list of tables that exist after execution.
        """
        sql_content = sql_path.read_text(encoding="utf-8")

        # Split into individual statements for ALTER TABLE handling
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]

        for stmt in statements:
            if not stmt:
                continue
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                error_msg = str(e).lower()
                # Handle idempotent ALTER TABLE (duplicate column)
                if "duplicate column" in error_msg:
                    logger.debug(f"Column already exists, skipping: {e}")
                    continue
                # Handle "table already exists" for non-IF-NOT-EXISTS
                if "already exists" in error_msg:
                    logger.debug(f"Object already exists, skipping: {e}")
                    continue
                raise

        conn.commit()

        # Get list of all tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]

    def _apply_governance_columns(self, conn: sqlite3.Connection) -> None:
        """Add governance columns to existing entries table (idempotent)."""
        for col_def in [
            "ALTER TABLE entries ADD COLUMN created_at TEXT DEFAULT ''",
            "ALTER TABLE entries ADD COLUMN expires_at TEXT DEFAULT ''",
        ]:
            try:
                conn.execute(col_def)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    logger.debug(f"Column already exists: {e}")
                else:
                    raise

        # Backfill created_at from timestamp
        conn.execute(
            "UPDATE entries SET created_at = datetime(timestamp, 'unixepoch') "
            "WHERE created_at = '' OR created_at IS NULL"
        )
        conn.commit()

    def run(self) -> MigrationResult:
        """Run all unapplied migrations.

        Returns:
            MigrationResult with success status, timing, and memory info.
        """
        tracemalloc.start()
        start_time = time.perf_counter()

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            self._ensure_schema_version_table(conn)
            applied = self._get_applied_versions(conn)
            migrations = self._discover_migrations()

            tables_created = []
            latest_version = 0

            for version, sql_path, description in migrations:
                if version in applied:
                    logger.debug(f"Migration v{version} already applied, skipping")
                    continue

                logger.info(f"Applying migration v{version}: {description}")
                tables = self._apply_sql_file(conn, sql_path)
                tables_created = tables

                # Apply governance columns on entries table
                self._apply_governance_columns(conn)

                # Record version
                conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, description),
                )
                conn.commit()
                latest_version = version
                logger.info(f"Migration v{version} applied successfully")

            if not migrations or all(v in applied for v, _, _ in migrations):
                # No new migrations to apply
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                    "AND name NOT LIKE 'sqlite_%'"
                )
                tables_created = [row[0] for row in cursor.fetchall()]
                if applied:
                    latest_version = max(applied)

            elapsed = time.perf_counter() - start_time
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_mb = peak / (1024 * 1024)

            conn.close()

            return MigrationResult(
                success=True,
                elapsed_seconds=elapsed,
                peak_memory_mb=peak_mb,
                tables_created=tables_created,
                version=latest_version,
            )

        except Exception as e:
            elapsed = time.perf_counter() - start_time
            try:
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peak_mb = peak / (1024 * 1024)
            except RuntimeError:
                peak_mb = 0.0

            logger.exception(f"Migration failed: {e}")
            return MigrationResult(
                success=False,
                elapsed_seconds=elapsed,
                peak_memory_mb=peak_mb,
                error=str(e),
            )
