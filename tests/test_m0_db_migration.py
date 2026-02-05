import importlib
import sqlite3
from pathlib import Path


def _prepare_legacy_db(tmp_path: Path, monkeypatch, legacy_device_id: str = "legacy"):
    server_dir = tmp_path / "server"
    client_dir = tmp_path / "client"
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(server_dir))
    monkeypatch.setenv("OPENRECALL_LEGACY_DEVICE_ID", legacy_device_id)

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    settings = openrecall.shared.config.settings
    settings.ensure_directories()

    db_path = settings.db_path
    with sqlite3.connect(str(db_path)) as conn:
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")
        conn.execute(
            "INSERT INTO entries (timestamp, app, title, text, description, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1234, "App", "Title", "Text", "Desc", "COMPLETED"),
        )
        conn.commit()

    import openrecall.server.database.sql

    importlib.reload(openrecall.server.database.sql)
    return settings, openrecall.server.database.sql


def test_m0_migration_removes_timestamp_unique_adds_device_client_ts_unique(
    tmp_path, monkeypatch
):
    settings, sql_module = _prepare_legacy_db(tmp_path, monkeypatch)
    sql_module.SQLStore()

    with sqlite3.connect(str(settings.db_path)) as conn:
        index_rows = conn.execute("PRAGMA index_list(entries)").fetchall()
        unique_indexes = [row for row in index_rows if row[2] == 1]
        unique_columns = []
        for index in unique_indexes:
            columns = [
                column[2]
                for column in conn.execute(
                    f"PRAGMA index_info('{index[1]}')"
                ).fetchall()
            ]
            unique_columns.append(columns)

    assert ["device_id", "client_ts"] in unique_columns
    assert all("timestamp" not in columns for columns in unique_columns)


def test_m0_migration_backfills_legacy_device_id(tmp_path, monkeypatch):
    settings, sql_module = _prepare_legacy_db(
        tmp_path, monkeypatch, legacy_device_id="legacy-device"
    )
    sql_module.SQLStore()

    with sqlite3.connect(str(settings.db_path)) as conn:
        row = conn.execute(
            """SELECT device_id, client_ts, client_tz, client_seq, image_hash,
                      server_received_at, image_relpath
               FROM entries"""
        ).fetchone()

    assert row[0] == "legacy-device"
    assert row[1] == 1234 * 1000
    assert row[2] is None
    assert row[3] is None
    assert row[4] is None
    assert row[5] == 1234 * 1000
    assert row[6] == "1234.png"


def test_m0_migration_creates_backup_file(tmp_path, monkeypatch):
    settings, sql_module = _prepare_legacy_db(tmp_path, monkeypatch)
    sql_module.SQLStore()

    backup_files = list(settings.db_path.parent.glob("recall.db.bak_m0_*"))
    assert backup_files


def test_m0_migration_is_idempotent(tmp_path, monkeypatch):
    settings, sql_module = _prepare_legacy_db(tmp_path, monkeypatch)
    sql_module.SQLStore()
    sql_module.SQLStore()

    with sqlite3.connect(str(settings.db_path)) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(entries)").fetchall()
        }

    assert "device_id" in columns
