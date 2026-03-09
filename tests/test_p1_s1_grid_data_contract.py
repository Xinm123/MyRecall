import sqlite3
from pathlib import Path

import pytest

from openrecall.server import __main__ as server_main
from openrecall.server.database.frames_store import FramesStore


@pytest.mark.unit
def test_claim_frame_accepts_active_app_window_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    store = FramesStore(db_path=db_path)
    capture_id = "0195689e-31bd-7ddf-b6d8-5f955dc6d6f0"
    metadata: dict[str, object] = {
        "timestamp": "2026-03-09T11:22:33Z",
        "active_app": "Visual Studio Code",
        "active_window": "test_file.py - MyRecall",
    }

    frame_id, is_new = store.claim_frame(capture_id=capture_id, metadata=metadata)

    assert is_new is True
    assert frame_id > 0

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT app_name, window_name FROM frames WHERE id = ?",
            (frame_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "Visual Studio Code"
    assert row[1] == "test_file.py - MyRecall"


@pytest.mark.unit
def test_get_recent_memories_normalizes_status_uppercase(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"
    server_main.ensure_v3_schema(db_path=db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO frames (
                capture_id, timestamp, app_name, window_name, browser_url,
                focused, capture_trigger, snapshot_path, image_size_bytes,
                status, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "0195689e-31bd-7ddf-b6d8-5f955dc6d6f1",
                "2026-03-09T11:33:44Z",
                "Terminal",
                "zsh",
                None,
                None,
                "idle",
                "/tmp/fake.jpg",
                123,
                "pending",
                "2026-03-09T11:33:45Z",
            ),
        )
        conn.commit()

    store = FramesStore(db_path=db_path)
    memories = store.get_recent_memories(limit=10)

    assert len(memories) == 1
    assert memories[0]["status"] == "PENDING"
