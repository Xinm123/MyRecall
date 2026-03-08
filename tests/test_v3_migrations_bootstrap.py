import sqlite3
from pathlib import Path

from openrecall.server import __main__ as server_main
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def test_run_migrations_tolerates_self_recording_sql(tmp_path: Path) -> None:
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
        run_migrations(conn, migrations_dir)

    with sqlite3.connect(db_path) as conn:
        assert _has_table(conn, "sample_data")
        count_row = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='20260101010101'"
        ).fetchone()
        assert count_row is not None
        assert count_row[0] == 1


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
