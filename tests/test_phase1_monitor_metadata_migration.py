"""Tests for monitor metadata schema and persistence."""

import sqlite3


def test_migration_adds_monitor_columns(tmp_path):
    from openrecall.server.database.migrations.runner import MigrationRunner

    db_path = tmp_path / "recall.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE entries (
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
    conn.commit()
    conn.close()

    result = MigrationRunner(db_path).run()
    assert result.success

    conn = sqlite3.connect(str(db_path))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(video_chunks)").fetchall()}
    conn.close()

    expected = {
        "monitor_id",
        "monitor_width",
        "monitor_height",
        "monitor_is_primary",
        "monitor_backend",
        "monitor_fingerprint",
        "app_name",
        "window_name",
    }
    assert expected.issubset(columns)


def test_insert_video_chunk_persists_monitor_metadata(tmp_path, monkeypatch):
    import importlib

    from openrecall.server.database.migrations.runner import MigrationRunner

    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    from openrecall.server.database.sql import SQLStore

    db_path = tmp_path / "MRS" / "db" / "recall.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE entries (
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
    conn.commit()
    conn.close()

    result = MigrationRunner(db_path).run()
    assert result.success

    store = SQLStore()
    chunk_id = store.insert_video_chunk(
        file_path="/tmp/chunk.mp4",
        device_name="display-main",
        checksum="abc123",
        app_name="Cursor",
        window_name="settings.json",
        monitor_id="42",
        monitor_width=3840,
        monitor_height=2160,
        monitor_is_primary=1,
        monitor_backend="sck",
        monitor_fingerprint="3840x2160:1",
    )

    assert chunk_id is not None

    row = store.get_video_chunk_by_id(chunk_id)
    assert row is not None
    assert row["monitor_id"] == "42"
    assert row["monitor_width"] == 3840
    assert row["monitor_height"] == 2160
    assert row["monitor_is_primary"] == 1
    assert row["monitor_backend"] == "sck"
    assert row["monitor_fingerprint"] == "3840x2160:1"
    assert row["app_name"] == "Cursor"
    assert row["window_name"] == "settings.json"


def test_sql_store_init_auto_applies_video_migrations(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    from openrecall.server.database.sql import SQLStore

    # SQLStore init should auto-create core tables and run migrations.
    SQLStore()

    db_path = tmp_path / "MRS" / "db" / "recall.db"
    conn = sqlite3.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    columns = {row[1] for row in conn.execute("PRAGMA table_info(video_chunks)").fetchall()}
    conn.close()

    assert "schema_version" in tables
    assert "video_chunks" in tables
    assert "status" in columns
    assert "monitor_id" in columns
