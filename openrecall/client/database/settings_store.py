"""SQLite-backed store for client-side settings."""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ClientSettingsStore:
    """SQLite-backed store for client-side settings.

    Stores configuration in client.db within the client data directory
    (e.g., ~/.myrecall/client/client.db) for persistence across restarts.
    Supports hot-reload by allowing runtime updates.
    """

    # Default settings applied on first run or reset
    DEFAULTS: dict[str, str] = {
        "edge_base_url": "",
        "capture_save_local_copies": "false",
        "capture_permission_poll_sec": "10",
        "debounce.click_ms": "3000",
        "debounce.trigger_ms": "3000",
        "debounce.capture_ms": "3000",
        "debounce.idle_interval_ms": "60000",
        "stats.interval_sec": "120",
    }

    def __init__(self, db_path: Path):
        """Initialize the settings store.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()
        self._ensure_defaults()

    def _ensure_tables(self) -> None:
        """Create the client_settings table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS client_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_client_settings_key ON client_settings(key)
            """)
            conn.commit()

    def _ensure_defaults(self) -> None:
        """Ensure default settings exist in the database."""
        with sqlite3.connect(self.db_path) as conn:
            for key, value in self.DEFAULTS.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO client_settings (key, value) VALUES (?, ?)
                    """,
                    (key, value),
                )
            conn.commit()

    def get(self, key: str, default: str = "") -> str:
        """Get a setting value by key.

        Args:
            key: The setting key
            default: Default value if key doesn't exist

        Returns:
            The setting value or default
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM client_settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        """Set a setting value.

        Args:
            key: The setting key
            value: The setting value
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO client_settings (key, value, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value),
            )
            conn.commit()
        logger.debug(f"Setting updated: {key} = {value}")

    def get_all(self) -> dict[str, str]:
        """Get all settings as a dictionary.

        Returns:
            Dictionary of all settings
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM client_settings")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
        with sqlite3.connect(self.db_path) as conn:
            for key, value in self.DEFAULTS.items():
                conn.execute(
                    """
                    INSERT INTO client_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value),
                )
            conn.commit()
        logger.info("Settings reset to defaults")
