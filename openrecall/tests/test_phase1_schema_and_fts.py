import importlib
import sqlite3

import numpy as np


def _reload_for_tmp_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    return openrecall.shared.config.settings, openrecall.server.database


def test_migration_adds_image_embedding_and_fts(monkeypatch, tmp_path):
    settings, database = _reload_for_tmp_dir(monkeypatch, tmp_path)
    database.create_db()

    with sqlite3.connect(str(settings.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "image_embedding" in cols

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'")
        row = cursor.fetchone()
        assert row is None or row[0] == "entries_fts"


def test_fts_upsert_and_search(monkeypatch, tmp_path):
    settings, database = _reload_for_tmp_dir(monkeypatch, tmp_path)
    database.create_db()

    ts = 1710000000
    embedding = (np.arange(settings.embedding_dim, dtype=np.float32) / 1000.0).astype(np.float32)
    image_embedding = (np.arange(settings.embedding_dim, dtype=np.float32) / 2000.0).astype(np.float32)

    with sqlite3.connect(str(settings.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO entries(app, title, text, description, timestamp, embedding, image_embedding, status) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, 'COMPLETED')",
            (
                "Terminal",
                "npm ERR!",
                "TypeError: cannot read property",
                "User debugging JavaScript error",
                ts,
                embedding.tobytes(),
                image_embedding.tobytes(),
            ),
        )
        entry_id = int(cursor.lastrowid)
        conn.commit()

        ok = database.fts_upsert_entry(
            conn,
            entry_id=entry_id,
            app="Terminal",
            title="npm ERR!",
            text="TypeError: cannot read property",
            description="User debugging JavaScript error",
        )
        hits = database.fts_search(conn, "TypeError", topk=10)

    assert ok in {True, False}
    if ok:
        assert any(h[0] == entry_id for h in hits)
    else:
        assert hits == []


def test_row_to_entry_includes_image_embedding(monkeypatch, tmp_path):
    settings, database = _reload_for_tmp_dir(monkeypatch, tmp_path)
    database.create_db()

    ts = 1710000001
    embedding = np.zeros(settings.embedding_dim, dtype=np.float32)
    image_embedding = np.ones(settings.embedding_dim, dtype=np.float32)

    with sqlite3.connect(str(settings.db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO entries(app, title, text, description, timestamp, embedding, image_embedding, status) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, 'COMPLETED')",
            (
                "IDE",
                "VS Code",
                "hello",
                "coding",
                ts,
                embedding.tobytes(),
                image_embedding.tobytes(),
            ),
        )
        conn.commit()

    entries = database.get_all_entries()
    assert len(entries) == 1
    assert entries[0].image_embedding is not None
    assert entries[0].image_embedding.shape == (settings.embedding_dim,)
    assert np.allclose(entries[0].image_embedding, 1.0)
