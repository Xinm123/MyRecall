"""Tests for FramesStore description CRUD methods."""
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


class TestDescriptionCRUD:
    def test_insert_and_get_description(self, store, temp_db):
        conn = store._connect()
        with conn:
            # Insert a frame first
            frame_id, _ = store.claim_frame(
                capture_id="cap_desc_test_001",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )

            # Enqueue
            store.insert_description_task(conn, frame_id)

            # Insert description
            store.insert_frame_description(
                conn,
                frame_id=frame_id,
                narrative="Test narrative",
                summary="Test summary",
                tags_json=json.dumps(["github", "coding", "browsing"]),
            )

            # Get
            desc = store.get_frame_description(conn, frame_id)
            assert desc is not None
            assert desc["narrative"] == "Test narrative"
            assert desc["summary"] == "Test summary"
            assert desc["tags"] == ["github", "coding", "browsing"]

    def test_queue_status(self, store):
        conn = store._connect()
        with conn:
            status = store.get_description_queue_status(conn)
            assert isinstance(status, dict)
            assert "pending" in status
            assert "completed" in status
            assert "processing" in status
            assert "failed" in status

    def test_claim_description_task(self, store):
        conn = store._connect()
        with conn:
            frame_id, _ = store.claim_frame(
                capture_id="cap_desc_test_002",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )
            store.insert_description_task(conn, frame_id)

        # Claim in a new connection
        conn2 = store._connect()
        with conn2:
            task = store.claim_description_task(conn2)
            assert task is not None
            assert task["frame_id"] == frame_id

    def test_complete_description_task(self, store):
        conn = store._connect()
        with conn:
            frame_id, _ = store.claim_frame(
                capture_id="cap_desc_test_003",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )
            store.insert_description_task(conn, frame_id)

        conn2 = store._connect()
        with conn2:
            task = store.claim_description_task(conn2)
            assert task is not None
            task_id = task["id"]

        conn3 = store._connect()
        with conn3:
            store.complete_description_task(conn3, task_id, frame_id)
            status = store.get_description_queue_status(conn3)
            assert status["completed"] >= 1

    def test_get_recent_descriptions(self, store):
        conn = store._connect()
        with conn:
            frame_id, _ = store.claim_frame(
                capture_id="cap_desc_test_004",
                metadata={
                    "capture_trigger": "manual",
                    "app_name": "TestApp",
                    "timestamp": "2026-03-24T10:00:00Z",
                },
            )
            store.insert_description_task(conn, frame_id)
            store.insert_frame_description(
                conn,
                frame_id=frame_id,
                narrative="Recent narrative",
                summary="Recent summary",
                tags_json=json.dumps(["github", "coding"]),
            )

        conn2 = store._connect()
        with conn2:
            descriptions = store.get_recent_descriptions(
                conn2,
                "2026-01-01T00:00:00Z",
                "2027-01-01T00:00:00Z",
                10,
            )
            assert len(descriptions) >= 1
            desc = descriptions[0]
            assert desc["frame_id"] == frame_id
            assert desc["summary"] == "Recent summary"
            assert desc["tags"] == ["github", "coding"]

    def test_frame_description_task_enqueues_pending_status(self, store):
        conn = store._connect()
        with conn:
            frame_id, _ = store.claim_frame(
                capture_id="cap_desc_test_005",
                metadata={"capture_trigger": "manual", "app_name": "TestApp"},
            )
            store.insert_description_task(conn, frame_id)

        conn2 = store._connect()
        with conn2:
            status = store.get_description_queue_status(conn2)
            assert status["pending"] >= 1
