import importlib
import sqlite3


def _setup_sql_store(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    client_dir = tmp_path / "client"
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(server_dir))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(client_dir))
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(server_dir))

    import openrecall.shared.config

    importlib.reload(openrecall.shared.config)
    settings = openrecall.shared.config.settings
    settings.ensure_directories()

    import openrecall.server.database.sql

    importlib.reload(openrecall.server.database.sql)
    store = openrecall.server.database.sql.SQLStore()
    return store, settings


def test_insert_pending_entry_v1_persists_device_and_client_ts(tmp_path, monkeypatch):
    store, settings = _setup_sql_store(tmp_path, monkeypatch)

    entry_id = store.insert_pending_entry_v1(
        device_id="device-1",
        client_ts=1700000000000,
        client_tz="UTC",
        client_seq=7,
        image_hash="hash-abc",
        app="TestApp",
        title="TestTitle",
        server_received_at=1700000001111,
        image_relpath="images/1700000000.png",
        timestamp=1700000000,
    )

    with sqlite3.connect(str(settings.db_path)) as conn:
        row = conn.execute(
            "SELECT device_id, client_ts, client_tz, client_seq, image_hash, "
            "app, title, status, server_received_at, image_relpath, timestamp "
            "FROM entries WHERE id = ?",
            (entry_id,),
        ).fetchone()

    assert row[0] == "device-1"
    assert row[1] == 1700000000000
    assert row[2] == "UTC"
    assert row[3] == 7
    assert row[4] == "hash-abc"
    assert row[5] == "TestApp"
    assert row[6] == "TestTitle"
    assert row[7] == "PENDING"
    assert row[8] == 1700000001111
    assert row[9] == "images/1700000000.png"
    assert row[10] == 1700000000


def test_get_entry_by_device_client_ts_returns_existing(tmp_path, monkeypatch):
    store, _ = _setup_sql_store(tmp_path, monkeypatch)

    entry_id = store.insert_pending_entry_v1(
        device_id="device-2",
        client_ts=1700000002000,
        client_tz=None,
        client_seq=None,
        image_hash="hash-def",
        app="TestApp",
        title="TestTitle",
        server_received_at=1700000002333,
        image_relpath="images/1700000002.png",
        timestamp=None,
    )

    entry = store.get_entry_by_device_client_ts("device-2", 1700000002000)

    assert entry == {
        "id": entry_id,
        "device_id": "device-2",
        "client_ts": 1700000002000,
        "image_hash": "hash-def",
        "status": "PENDING",
        "server_received_at": 1700000002333,
        "image_relpath": "images/1700000002.png",
    }


def test_get_entry_by_device_client_ts_returns_none_for_missing(tmp_path, monkeypatch):
    store, _ = _setup_sql_store(tmp_path, monkeypatch)

    entry = store.get_entry_by_device_client_ts("missing-device", 123)

    assert entry is None
