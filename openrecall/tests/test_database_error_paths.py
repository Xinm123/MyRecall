import sqlite3

import numpy as np


def test_create_db_handles_sqlite_error(monkeypatch):
    import openrecall.server.database as db

    monkeypatch.setattr(db.sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("boom")))
    db.create_db()


def test_row_to_entry_defaults_status_when_missing():
    import openrecall.server.database as db

    class FakeRow:
        def __getitem__(self, key):
            if key == "status":
                raise KeyError(key)
            values = {
                "id": 1,
                "app": "A",
                "title": "T",
                "text": "x",
                "description": None,
                "timestamp": 1,
                "embedding": np.zeros((8,), dtype=np.float32).tobytes(),
            }
            return values[key]

    entry = db._row_to_entry(FakeRow())  # type: ignore[arg-type]
    assert entry.status == "COMPLETED"


def test_db_read_helpers_handle_sqlite_error(monkeypatch):
    import openrecall.server.database as db

    monkeypatch.setattr(db.sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("boom")))
    assert db.get_all_entries() == []
    assert db.get_all_entries_with_status() == []
    assert db.get_timestamps() == []
    assert db.get_entries_by_time_range(0, 1) == []
    assert db.get_entries_since(0) == []
    assert db.get_entries_until(1) == []


def test_insert_entry_handles_sqlite_error(monkeypatch):
    import openrecall.server.database as db

    monkeypatch.setattr(db.sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("boom")))
    out = db.insert_entry(
        text="t",
        timestamp=1,
        embedding=np.zeros((8,), dtype=np.float32),
        app="A",
        title="T",
    )
    assert out is None


def test_insert_pending_entry_duplicate_and_error(flask_app, monkeypatch):
    import openrecall.server.database as db

    task_id = db.insert_pending_entry(timestamp=1, app="A", title="T", image_path="x")
    assert task_id is not None
    task_id2 = db.insert_pending_entry(timestamp=1, app="A", title="T", image_path="x")
    assert task_id2 is None

    monkeypatch.setattr(db.sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("boom")))
    assert db.insert_pending_entry(timestamp=2, app="A", title="T", image_path="x") is None


def test_async_db_helpers_error_branches(monkeypatch):
    import openrecall.server.database as db

    class BadConn:
        def cursor(self):
            raise sqlite3.Error("boom")

    assert db.get_pending_count(BadConn()) == 0
    assert db.get_next_task(BadConn(), lifo_mode=False) is None
    assert db.reset_stuck_tasks(BadConn()) == 0
    assert db.mark_task_processing(BadConn(), 1) is False
    assert db.mark_task_completed(BadConn(), 1, "t", None, np.zeros((8,), dtype=np.float32)) is False
    assert db.mark_task_failed(BadConn(), 1) is False

    monkeypatch.setattr(db.sqlite3, "connect", lambda *a, **k: (_ for _ in ()).throw(sqlite3.Error("boom")))
    assert db.get_pending_count() == 0
    assert db.reset_stuck_tasks() == 0

