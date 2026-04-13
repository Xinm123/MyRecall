"""Tests for batch description fetch in FramesStore."""
import json
import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db):
    return FramesStore(db_path=temp_db)


class TestGetFrameDescriptionsBatch:
    def test_get_frame_descriptions_batch_returns_dict(self, store):
        """Store returns empty dict for empty DB."""
        result = store.get_frame_descriptions_batch([])
        assert result == {}

    def test_get_frame_descriptions_batch_empty_input(self, store):
        """Empty input returns empty dict."""
        result = store.get_frame_descriptions_batch([])
        assert result == {}

    def test_get_frame_descriptions_batch_returns_only_completed(
        self, store, temp_db
    ):
        """Only returns descriptions for frames with description_status='completed'."""
        conn = store._connect()
        with conn:
            # Insert two frames
            fid1, _ = store.claim_frame(
                capture_id="cap_batch_001",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )
            fid2, _ = store.claim_frame(
                capture_id="cap_batch_002",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )

            # Insert description for frame 1
            store.insert_description_task(conn, fid1)
            store.insert_frame_description(
                conn,
                frame_id=fid1,
                narrative="Narrative 1",
                summary="Summary 1",
                tags_json=json.dumps(["tag1", "tag2"]),
            )
            # Mark frame 1 as completed
            conn.execute(
                "UPDATE frames SET description_status = 'completed' WHERE id = ?",
                (fid1,),
            )

            # Insert description for frame 2 but leave status as 'pending'
            store.insert_description_task(conn, fid2)
            store.insert_frame_description(
                conn,
                frame_id=fid2,
                narrative="Narrative 2",
                summary="Summary 2",
                tags_json=json.dumps(["tag3"]),
            )
            # Do NOT mark frame 2 as completed

            conn.commit()
            result = store.get_frame_descriptions_batch([fid1, fid2])

        # Only frame 1 should be in the result (completed)
        assert fid1 in result
        assert fid2 not in result
        assert result[fid1]["narrative"] == "Narrative 1"
        assert result[fid1]["summary"] == "Summary 1"
        assert result[fid1]["tags"] == ["tag1", "tag2"]

    def test_get_frame_descriptions_batch_multiple_completed(
        self, store, temp_db
    ):
        """Returns dict with multiple completed descriptions."""
        conn = store._connect()
        with conn:
            fid1, _ = store.claim_frame(
                capture_id="cap_batch_multi_001",
                metadata={"capture_trigger": "manual", "app_name": "App1"},
            )
            fid2, _ = store.claim_frame(
                capture_id="cap_batch_multi_002",
                metadata={"capture_trigger": "manual", "app_name": "App2"},
            )
            fid3, _ = store.claim_frame(
                capture_id="cap_batch_multi_003",
                metadata={"capture_trigger": "manual", "app_name": "App3"},
            )

            for fid in [fid1, fid2, fid3]:
                store.insert_description_task(conn, fid)
                store.insert_frame_description(
                    conn,
                    frame_id=fid,
                    narrative=f"Narrative for {fid}",
                    summary=f"Summary for {fid}",
                    tags_json=json.dumps([f"tag{fid}"]),
                )
                conn.execute(
                    "UPDATE frames SET description_status = 'completed' WHERE id = ?",
                    (fid,),
                )

            conn.commit()
            result = store.get_frame_descriptions_batch([fid1, fid2, fid3])

        assert len(result) == 3
        assert fid1 in result
        assert fid2 in result
        assert fid3 in result
        assert result[fid1]["narrative"] == f"Narrative for {fid1}"
        assert result[fid2]["summary"] == f"Summary for {fid2}"
        assert result[fid3]["tags"] == [f"tag{fid3}"]

    def test_get_frame_descriptions_batch_nonexistent_ids(self, store, temp_db):
        """Returns empty dict for nonexistent frame IDs."""
        conn = store._connect()
        with conn:
            fid1, _ = store.claim_frame(
                capture_id="cap_batch_ne_001",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )
            store.insert_description_task(conn, fid1)
            store.insert_frame_description(
                conn,
                frame_id=fid1,
                narrative="N",
                summary="S",
                tags_json=json.dumps([]),
            )
            conn.execute(
                "UPDATE frames SET description_status = 'completed' WHERE id = ?",
                (fid1,),
            )

            conn.commit()
            result = store.get_frame_descriptions_batch([fid1, 99999, -1])

        # Only the real completed frame is returned
        assert fid1 in result
        assert 99999 not in result
        assert -1 not in result
