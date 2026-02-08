"""Phase 1 tests: Timeline API, Frame serving, and Video upload API."""
import importlib
import io
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _seed_video_data(db_path: Path, frames_path: Path, num_frames: int = 5):
    """Seed database with video chunk, frames, and OCR text."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO video_chunks (file_path, device_name, status) VALUES (?, ?, ?)",
        ("/tmp/test.mp4", "primary", "COMPLETED"),
    )
    chunk_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for i in range(num_frames):
        conn.execute(
            "INSERT INTO frames (video_chunk_id, offset_index, timestamp, app_name, window_name) VALUES (?, ?, ?, ?, ?)",
            (chunk_id, i, 1000.0 + i * 5, "TestApp", f"Window {i}"),
        )
        frame_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length) VALUES (?, ?, ?)",
            (frame_id, f"OCR text for frame {i}", 20),
        )
        # Create frame PNG
        frames_path.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(str(frames_path / f"{frame_id}.png"))

    conn.commit()
    conn.close()
    return chunk_id


@pytest.fixture
def app_with_data(tmp_path, monkeypatch):
    """Flask app with seeded video data."""
    import unittest.mock as mock

    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    openrecall.server.database.SQLStore()

    # Create video-specific tables (SQLStore._init_db only creates entries)
    from openrecall.shared.config import settings
    db_path = settings.db_path
    frames_path = settings.frames_path
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING')")
    conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    conn.close()

    import openrecall.server.auth
    importlib.reload(openrecall.server.auth)

    import openrecall.server.search.engine
    mock_se = mock.MagicMock()
    mock_se.search.return_value = []
    monkeypatch.setattr(openrecall.server.search.engine, "SearchEngine", lambda: mock_se)

    import openrecall.server.api
    importlib.reload(openrecall.server.api)
    import openrecall.server.api_v1
    importlib.reload(openrecall.server.api_v1)
    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    _seed_video_data(db_path, frames_path, num_frames=5)

    return openrecall.server.app.app


@pytest.fixture
def client(app_with_data):
    app_with_data.config["TESTING"] = True
    with app_with_data.test_client() as c:
        yield c


class TestTimelineAPI:
    """Gate 1-F-04: Timeline API."""

    def test_timeline_returns_paginated_response(self, client):
        """Timeline endpoint returns paginated envelope."""
        resp = client.get("/api/v1/timeline?start_time=0&end_time=9999999&limit=50&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] == 5

    def test_timeline_time_range_filter(self, client):
        """Timeline filters by time range."""
        resp = client.get("/api/v1/timeline?start_time=1005&end_time=1015")
        assert resp.status_code == 200
        data = resp.get_json()
        # Frames at 1005, 1010, 1015 = 3
        assert data["meta"]["total"] == 3

    def test_timeline_pagination(self, client):
        """Timeline respects limit and offset."""
        resp = client.get("/api/v1/timeline?start_time=0&end_time=9999999&limit=2&offset=0")
        data = resp.get_json()
        assert len(data["data"]) == 2
        assert data["meta"]["has_more"] is True

        resp2 = client.get("/api/v1/timeline?start_time=0&end_time=9999999&limit=2&offset=2")
        data2 = resp2.get_json()
        assert len(data2["data"]) == 2

    def test_timeline_frame_urls(self, client):
        """Timeline entries include frame_url."""
        resp = client.get("/api/v1/timeline?start_time=0&end_time=9999999")
        data = resp.get_json()
        for frame in data["data"]:
            assert "frame_url" in frame
            assert frame["frame_url"].startswith("/api/v1/frames/")

    def test_timeline_empty_range(self, client):
        """Timeline returns empty for out-of-range times."""
        resp = client.get("/api/v1/timeline?start_time=9999990&end_time=9999999")
        data = resp.get_json()
        assert data["meta"]["total"] == 0
        assert len(data["data"]) == 0

    def test_timeline_accepts_page_and_page_size(self, client):
        """Timeline supports page/page_size aliases for pagination."""
        resp = client.get("/api/v1/timeline?start_time=0&end_time=9999999&page=2&page_size=2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["limit"] == 2
        assert data["meta"]["offset"] == 2
        assert len(data["data"]) == 2

    def test_timeline_limit_offset_take_precedence_over_page_aliases(self, client):
        """Legacy limit/offset should win when both pagination styles are provided."""
        resp = client.get(
            "/api/v1/timeline?start_time=0&end_time=9999999&limit=3&offset=1&page=3&page_size=1"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["limit"] == 3
        assert data["meta"]["offset"] == 1

    def test_legacy_timeline_page_uses_frame_urls(self, client):
        """Legacy /timeline page should render image URLs for extracted frames."""
        resp = client.get("/timeline")
        assert resp.status_code == 200
        assert b"/api/v1/frames/" in resp.data

    def test_legacy_memories_recent_returns_frame_image_url(self, client):
        """Legacy /api/memories/recent should expose frame-backed image_url."""
        resp = client.get("/api/memories/recent?limit=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["image_url"].startswith("/api/v1/frames/")


class TestFrameServingAPI:
    """Test frame image serving."""

    def test_serve_existing_frame(self, client):
        """Serving an existing frame returns PNG image."""
        resp = client.get("/api/v1/frames/1")
        assert resp.status_code == 200
        assert resp.content_type in ("image/png", "image/png; charset=utf-8")

    def test_serve_nonexistent_frame(self, client):
        """Serving a nonexistent frame returns 404."""
        resp = client.get("/api/v1/frames/99999")
        assert resp.status_code == 404


class TestVideoUploadAPI:
    """Test video upload endpoint."""

    def test_upload_video_chunk(self, client, tmp_path):
        """Upload a video chunk file."""
        metadata = json.dumps({
            "type": "video_chunk",
            "timestamp": 1234567890,
            "device_name": "test_device",
            "checksum": "",
        })
        video_data = b"fake video data " * 100
        resp = client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(video_data), "test_chunk.mp4", "video/mp4"),
                "metadata": metadata,
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "accepted"
        assert "chunk_id" in data

    def test_upload_screenshot_still_works(self, client):
        """Screenshot uploads still work (regression check)."""
        img = Image.new("RGB", (10, 10), color="red")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        metadata = json.dumps({
            "timestamp": 8888888,
            "app_name": "TestApp",
            "window_title": "TestWindow",
        })

        resp = client.post(
            "/api/v1/upload",
            data={"file": (img_bytes, "test.png"), "metadata": metadata},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202


class TestUploadStatusAPI:
    """Test upload status endpoint for resume support."""

    def test_upload_status_not_found(self, client):
        """Upload status for unknown checksum returns not_found."""
        resp = client.get("/api/v1/upload/status?checksum=nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "not_found"
        assert data["bytes_received"] == 0

    def test_upload_status_missing_checksum(self, client):
        """Upload status without checksum returns 400."""
        resp = client.get("/api/v1/upload/status")
        assert resp.status_code == 400


class TestSearchPaginationCompatibility:
    """Test /api/v1/search pagination parameter aliases."""

    def test_search_accepts_page_and_page_size_when_query_empty(self, client):
        """Empty-query search should still reflect pagination aliases in metadata."""
        resp = client.get("/api/v1/search?q=&page=2&page_size=20")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["limit"] == 20
        assert data["meta"]["offset"] == 20

    def test_search_limit_offset_take_precedence_when_both_styles_provided(self, client):
        """Legacy limit/offset takes precedence over page/page_size when both are set."""
        resp = client.get("/api/v1/search?q=&limit=7&offset=4&page=9&page_size=2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["limit"] == 7
        assert data["meta"]["offset"] == 4
