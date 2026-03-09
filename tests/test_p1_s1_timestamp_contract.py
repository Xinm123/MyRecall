import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from openrecall.client.spool import SpoolQueue
from openrecall.server.database.frames_store import FramesStore, _to_utc_iso8601


@pytest.mark.unit
def test_to_utc_iso8601_converts_unix_int() -> None:
    value = _to_utc_iso8601(1741434245)
    assert value is not None
    assert "T" in value
    assert value.endswith("Z")


@pytest.mark.unit
def test_to_utc_iso8601_converts_decimal_unix_string() -> None:
    value = _to_utc_iso8601("1741434245.123")
    assert value is not None
    assert "T" in value
    assert value.endswith("Z")


@pytest.mark.unit
def test_frames_store_last_frame_timestamp_normalized(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE frames (id INTEGER PRIMARY KEY, timestamp TIMESTAMP NOT NULL)"
        )
        conn.execute("INSERT INTO frames (timestamp) VALUES (?)", (1741434245,))
        conn.commit()

    store = FramesStore(db_path=db_path)
    ts = store.get_last_frame_timestamp()
    assert ts is not None
    assert "T" in ts
    assert ts.endswith("Z")


@pytest.mark.unit
def test_spool_default_timestamp_is_iso8601(tmp_path: Path) -> None:
    queue = SpoolQueue(storage_dir=tmp_path)
    image = Image.new("RGB", (2, 2), color=(10, 20, 30))
    capture_id = queue.enqueue(image, {})

    json_path = tmp_path / f"{capture_id}.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(payload.get("timestamp"), str)
    assert "T" in payload["timestamp"]
    assert payload["timestamp"].endswith("Z")
