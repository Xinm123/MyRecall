"""Tests for redesigned activity-summary description fields.

Verifies that descriptions include frame_id, timestamp, summary, intent, entities
(narrative removed) in the correct order.
"""
import json
import sqlite3
from pathlib import Path
import pytest
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db: Path) -> FramesStore:
    return FramesStore(db_path=temp_db)


def _create_frame_and_description(
    store: FramesStore, capture_id: str, timestamp: str, app_name: str,
    narrative: str, entities: list, intent: str, summary: str,
) -> int:
    frame_id, _ = store.claim_frame(
        capture_id=capture_id,
        metadata={"timestamp": timestamp, "app_name": app_name, "window_name": f"{app_name} Window"},
    )
    store.complete_accessibility_frame(
        frame_id=frame_id,
        text="frame text",
        browser_url=None,
        content_hash=None,
        simhash=None,
        accessibility_tree_json="[]",
        accessibility_text_content="frame text",
        accessibility_node_count=0,
        accessibility_truncated=False,
        elements=[],
    )
    with store._connect() as conn:
        store.insert_description_task(conn, frame_id)
        conn.commit()
        # Simulate completed description
        conn.execute(
            """INSERT OR REPLACE INTO frame_descriptions
               (frame_id, narrative, entities_json, intent, summary)
               VALUES (?, ?, ?, ?, ?)""",
            (frame_id, narrative, json.dumps(entities), intent, summary),
        )
        conn.execute(
            "UPDATE frames SET description_status = 'completed' WHERE id = ?",
            (frame_id,),
        )
        conn.commit()
    return frame_id


class TestDescriptionsNewFields:
    def test_descriptions_includes_timestamp(self, store: FramesStore):
        """Each description entry must include timestamp from frames table."""
        _create_frame_and_description(
            store, "cap-1", "2026-03-20T10:30:00Z", "Safari",
            "Test narrative", [], "testing", "Testing",
        )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert len(descs) == 1
        assert descs[0]["timestamp"] == "2026-03-20T10:30:00Z"

    def test_descriptions_excludes_narrative(self, store: FramesStore):
        """Descriptions should NOT include narrative field."""
        _create_frame_and_description(
            store, "cap-1", "2026-03-20T10:30:00Z", "Safari",
            "This is a very long narrative that should not appear",
            [], "testing", "Short summary",
        )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert len(descs) == 1
        assert "narrative" not in descs[0]
        assert "summary" in descs[0]
        assert "intent" in descs[0]
        assert "entities" in descs[0]

    def test_descriptions_has_frame_id_timestamp_summary_intent_entities(self, store: FramesStore):
        """Description must have exactly these 5 fields."""
        _create_frame_and_description(
            store, "cap-1", "2026-03-20T10:30:00Z", "Safari",
            "Narrative text", ["Claude Code", "API"], "coding", "Coding in Claude",
        )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert set(descs[0].keys()) == {"frame_id", "timestamp", "summary", "intent", "entities"}

    def test_descriptions_ordered_by_timestamp_desc(self, store: FramesStore):
        """Descriptions should be ordered by frame timestamp descending."""
        _create_frame_and_description(store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "N", [], "first", "First")
        _create_frame_and_description(store, "cap-2", "2026-03-20T10:30:00Z", "Safari", "N", [], "second", "Second")
        _create_frame_and_description(store, "cap-3", "2026-03-20T10:15:00Z", "Safari", "N", [], "middle", "Middle")

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 10)

        assert descs[0]["intent"] == "second"
        assert descs[1]["intent"] == "middle"
        assert descs[2]["intent"] == "first"

    def test_descriptions_respects_limit(self, store: FramesStore):
        """Descriptions should respect the limit parameter."""
        for i in range(5):
            _create_frame_and_description(
                store, f"cap-{i}", f"2026-03-20T10:{i:02d}:00Z", "Safari",
                "N", [], f"intent-{i}", f"Summary {i}",
            )

        with store._connect() as conn:
            descs = store.get_recent_descriptions(conn, "2026-03-20T09:00:00Z", "2026-03-20T11:00:00Z", 3)

        assert len(descs) == 3
