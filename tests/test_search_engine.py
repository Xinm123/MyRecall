"""Tests for SearchEngine class."""

import sqlite3
from pathlib import Path

import pytest

from openrecall.server.search.engine import SearchEngine


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with required schema via migrations."""
    db_path = tmp_path / "test.db"

    with sqlite3.connect(str(db_path)) as conn:
        # Run initial schema
        init_sql = Path("openrecall/server/database/migrations/20260227000001_initial_schema.sql").read_text()
        conn.executescript(init_sql)

        # Run intermediate migrations
        for mig in [
            "20260310121000_add_event_ts_to_frames.sql",
            "20260315140000_add_last_known_context_to_frames.sql",
            "20260317000001_ocr_text_unique_frame_id.sql",
            "20260321120000_dual_hash_storage.sql",
            "20260324120000_add_frame_description.sql",
            "20260325120000_consolidate_fts_to_full_text.sql",
            "20260408120000_description_fields_redesign.sql",
            "20260409120000_add_frame_embedding.sql",
            "20260414000000_add_visibility_status.sql",
            "20260426000000_add_local_timestamp.sql",
        ]:
            mig_sql = Path(f"openrecall/server/database/migrations/{mig}").read_text()
            conn.executescript(mig_sql)

    return db_path


def test_count_by_type_returns_ocr_and_accessibility_counts(test_db):
    """Test count_by_type returns counts for both content types."""
    engine = SearchEngine(db_path=test_db)

    # Insert test data - One OCR frame and one accessibility frame, both with full_text
    with sqlite3.connect(str(test_db)) as conn:
        # Insert OCR frame with full_text
        conn.execute(
            """INSERT INTO frames (capture_id, timestamp, local_timestamp, app_name, window_name, device_name, text_source, status, ingested_at, full_text, visibility_status)
               VALUES ('cap-ocr-001', '2024-01-01T00:00:00Z', '2024-01-01T08:00:00.000', 'TestApp', 'TestWindow', 'monitor_0', 'ocr', 'completed', '2024-01-01T00:00:00.000Z', 'test ocr content', 'queryable')"""
        )
        frame_id_ocr = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Also insert into ocr_text for completeness (FramesStore may still do this)
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length) VALUES (?, ?, ?)",
            (frame_id_ocr, "test ocr content", 16)
        )

        # Insert accessibility frame with full_text
        conn.execute(
            """INSERT INTO frames (capture_id, timestamp, local_timestamp, app_name, window_name, device_name, text_source, status, ingested_at, full_text, visibility_status)
               VALUES ('cap-ax-001', '2024-01-01T00:00:01Z', '2024-01-01T08:00:01.000', 'TestApp', 'TestWindow', 'monitor_0', 'accessibility', 'completed', '2024-01-01T00:00:01.000Z', 'test accessibility content', 'queryable')"""
        )
        frame_id_ax = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO accessibility (frame_id, text_content, text_length, app_name, window_name) VALUES (?, ?, ?, ?, ?)",
            (frame_id_ax, "test accessibility content", 26, "TestApp", "TestWindow")
        )

        conn.commit()

    # Search with matching query
    counts = engine.count_by_type(
        q="test",
        start_time=None,
        end_time=None,
        app_name=None,
        window_name=None,
        focused=None,
        browser_url=None,
    )

    assert "ocr" in counts
    assert "accessibility" in counts
    assert isinstance(counts["ocr"], int)
    assert isinstance(counts["accessibility"], int)
    assert counts["ocr"] == 1
    assert counts["accessibility"] == 1


def test_count_by_type_returns_zeros_on_empty_database(test_db):
    """Test count_by_type returns zeros for empty database."""
    engine = SearchEngine(db_path=test_db)

    counts = engine.count_by_type(q="nonexistent")

    assert counts["ocr"] == 0
    assert counts["accessibility"] == 0
