import sqlite3
from pathlib import Path

import pytest

from openrecall.server import __main__ as server_main
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import (
    run_migrations,
    verify_schema_integrity,
)


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def test_run_migrations_rejects_self_recording_sql(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    migrations_dir.joinpath("20260101010101_initial.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE IF NOT EXISTS sample_data(id INTEGER PRIMARY KEY);",
                "INSERT INTO schema_migrations(version, description) VALUES ('20260101010101', 'initial');",
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "edge.db"
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(ValueError):
            run_migrations(conn, migrations_dir)


def test_run_migrations_is_atomic_on_script_failure(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    migrations_dir.joinpath("20260101010101_broken.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE partial_data(id INTEGER PRIMARY KEY);",
                "INSERT INTO not_existing_table(x) VALUES (1);",
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "edge.db"
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.Error):
            run_migrations(conn, migrations_dir)

    with sqlite3.connect(db_path) as conn:
        assert not _has_table(conn, "partial_data")
        row = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='20260101010101'"
        ).fetchone()
        assert row is not None
        assert row[0] == 0


def test_verify_schema_integrity_detects_marked_but_missing_structure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "edge.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
            ("20260227000001", "initial_schema"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            verify_schema_integrity(conn)


def test_startup_bootstrap_creates_frames_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"

    server_main.ensure_v3_schema(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        assert _has_table(conn, "frames")


def test_frames_store_without_bootstrap_does_not_create_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"

    store = FramesStore(db_path=db_path)
    counts = store.get_queue_counts()

    assert counts == {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    with sqlite3.connect(db_path) as conn:
        assert not _has_table(conn, "frames")
