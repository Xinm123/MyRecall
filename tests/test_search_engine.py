"""Tests for SearchEngine class."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.search.engine import SearchEngine


@pytest.fixture
def test_db(tmp_path):
    """Create a test database with required schema."""
    db_path = tmp_path / "test.db"

    with sqlite3.connect(str(db_path)) as conn:
        # Create frames table
        conn.execute("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                app_name TEXT,
                window_name TEXT,
                browser_url TEXT,
                focused INTEGER,
                device_name TEXT,
                text_source TEXT,
                status TEXT DEFAULT 'completed'
            )
        """)

        # Create ocr_text table
        conn.execute("""
            CREATE TABLE ocr_text (
                id INTEGER PRIMARY KEY,
                frame_id INTEGER NOT NULL,
                text TEXT,
                text_length INTEGER DEFAULT 0,
                app_name TEXT,
                window_name TEXT,
                FOREIGN KEY (frame_id) REFERENCES frames(id)
            )
        """)

        # Create accessibility table
        conn.execute("""
            CREATE TABLE accessibility (
                id INTEGER PRIMARY KEY,
                frame_id INTEGER NOT NULL,
                text_content TEXT,
                text_length INTEGER DEFAULT 0,
                app_name TEXT,
                window_name TEXT,
                browser_url TEXT,
                FOREIGN KEY (frame_id) REFERENCES frames(id)
            )
        """)

        # Create FTS5 tables matching actual schema
        conn.execute("""
            CREATE VIRTUAL TABLE ocr_text_fts USING fts5(
                text,
                app_name,
                window_name,
                frame_id UNINDEXED,
                tokenize='unicode61'
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE frames_fts USING fts5(
                app_name,
                window_name,
                browser_url,
                focused,
                id UNINDEXED,
                tokenize='unicode61'
            )
        """)

        conn.execute("""
            CREATE VIRTUAL TABLE accessibility_fts USING fts5(
                text_content,
                app_name,
                window_name,
                browser_url,
                content='accessibility',
                content_rowid='id',
                tokenize='unicode61'
            )
        """)

        conn.commit()

    return db_path


def test_count_by_type_returns_ocr_and_accessibility_counts(test_db):
    """Test count_by_type returns counts for both content types."""
    engine = SearchEngine(db_path=test_db)

    # Insert test data - One OCR frame with matching text
    with sqlite3.connect(str(test_db)) as conn:
        # Insert OCR frame
        cursor = conn.execute(
            """INSERT INTO frames (timestamp, app_name, window_name, text_source, status)
               VALUES ('2024-01-01T00:00:00Z', 'TestApp', 'TestWindow', 'ocr', 'completed')"""
        )
        frame_id_ocr = cursor.lastrowid
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length) VALUES (?, ?, ?)",
            (frame_id_ocr, "test ocr content", 16)
        )
        # Insert into FTS - ocr_text_fts uses frame_id column, not rowid
        conn.execute(
            "INSERT INTO ocr_text_fts (frame_id, text, app_name, window_name) VALUES (?, ?, ?, ?)",
            (frame_id_ocr, "test ocr content", "TestApp", "TestWindow")
        )

        # Insert accessibility frame
        cursor = conn.execute(
            """INSERT INTO frames (timestamp, app_name, window_name, text_source, status)
               VALUES ('2024-01-01T00:00:01Z', 'TestApp', 'TestWindow', 'accessibility', 'completed')"""
        )
        frame_id_ax = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO accessibility (frame_id, text_content, text_length) VALUES (?, ?, ?)",
            (frame_id_ax, "test accessibility content", 26)
        )
        accessibility_id = cursor.lastrowid
        # Insert into FTS - use accessibility.id as rowid
        conn.execute(
            "INSERT INTO accessibility_fts (rowid, text_content, app_name, window_name, browser_url) VALUES (?, ?, ?, ?, ?)",
            (accessibility_id, "test accessibility content", "TestApp", "TestWindow", None)
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
        min_length=None,
        max_length=None,
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
