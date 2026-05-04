"""SQLite-backed store for server-side settings."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class ServerSettingsStore:
    """SQLite-backed store for server-side settings.

    Uses a SPARSE table: defaults are NOT pre-inserted. This gives the
    source-tag mechanism three distinct states (sqlite / toml / default).
    """

    DEFAULTS: dict[str, str] = {
        "description.provider": "local",
        "description.model": "",
        "description.api_key": "",
        "description.api_base": "",
        "description.request_timeout": "120",
    }

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value.

        Returns `default` (None by default) if the key has no row in SQLite.
        This differs from ClientSettingsStore which returns "" for missing keys
        because it uses a dense table with pre-inserted defaults.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM server_settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO server_settings (key, value, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, str(value)),
            )
            conn.commit()
        logger.debug(f"Server setting updated: {key}")

    def set_many(self, items: dict[str, str]) -> None:
        """Atomic batch write of multiple settings."""
        with sqlite3.connect(self.db_path) as conn:
            for key, value in items.items():
                conn.execute(
                    """
                    INSERT INTO server_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, str(value)),
                )
            conn.commit()
        logger.debug(f"Server settings batch updated: {list(items.keys())}")

    def apply_changes(
        self,
        deletes: list[str],
        sets: dict[str, str],
    ) -> None:
        """Atomic: delete keys + upsert keys in ONE transaction."""
        if not deletes and not sets:
            return
        with sqlite3.connect(self.db_path) as conn:
            for key in deletes:
                conn.execute("DELETE FROM server_settings WHERE key = ?", (key,))
            for key, value in sets.items():
                conn.execute(
                    """
                    INSERT INTO server_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, str(value)),
                )
            conn.commit()
        logger.debug(
            f"Server settings applied: deleted={deletes}, set={list(sets.keys())}"
        )

    def delete(self, key: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM server_settings WHERE key = ?", (key,))
            conn.commit()
        logger.debug(f"Server setting deleted: {key}")

    def get_all(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM server_settings")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def reset_to_defaults(self) -> None:
        """Delete all description.* keys from SQLite so reads fall through to TOML.

        Note: This differs from ClientSettingsStore.reset_to_defaults() which
        INSERTs/UPDATEs keys back to default values. Here we use a sparse
        table, so "reset" means DELETE to let runtime_config fall through.
        """
        with sqlite3.connect(self.db_path) as conn:
            for key in self.DEFAULTS:
                conn.execute("DELETE FROM server_settings WHERE key = ?", (key,))
            conn.commit()
        logger.info("Server description settings reset to defaults")
