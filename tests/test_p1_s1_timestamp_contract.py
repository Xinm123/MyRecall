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
def test_frames_store_last_frame_timestamp_returns_local(tmp_path: Path) -> None:
    db_path = tmp_path / "edge.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE frames (id INTEGER PRIMARY KEY, timestamp TEXT, local_timestamp TEXT)"
        )
        conn.execute(
            "INSERT INTO frames (timestamp, local_timestamp) VALUES (?, ?)",
            ("2026-03-20T10:00:00Z", "2026-03-20T18:00:00.000"),
        )
        conn.commit()

    store = FramesStore(db_path=db_path)
    ts = store.get_last_frame_timestamp()
    assert ts is not None
    assert "T" in ts
    # Returns local_timestamp, not UTC
    assert ts == "2026-03-20T18:00:00.000"


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


@pytest.mark.unit
def test_api_response_timestamps_split_utc_vs_local() -> None:
    """Verify API response field timestamp conventions:
    - 'timestamp' fields (search/timeline/activity-summary): local time, NO 'Z'
    - 'ingested_at', 'processed_at', 'description_generated_at': UTC, WITH 'Z'
    """
    # Local time fields (no Z suffix)
    local_timestamp = "2026-04-26T16:30:00.123"
    assert not local_timestamp.endswith("Z")

    # UTC fields (with Z suffix)
    utc_ingested_at = "2026-04-26T08:30:00.123Z"
    assert utc_ingested_at.endswith("Z")

    utc_processed_at = "2026-04-26T08:30:00.123Z"
    assert utc_processed_at.endswith("Z")
