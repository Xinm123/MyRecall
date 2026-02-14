"""Phase 2.5 Video Page tests — /video route returns 200, Alpine component, stats injection, etc.

Tests cover:
- GET /video returns 200
- Page extends layout (has header, toolbar)
- Video Alpine component present (videoDashboard)
- SSR stats injection (initialVideoStats)
- Empty state rendering
- Chunk table structure
- Video player element
- Frame gallery structure
"""

import json
import sqlite3
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_video_data(db_path: Path, video_dir: Path, frames_dir: Path):
    """Seed minimal video data for page rendering tests."""
    video_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Video chunk
    vf = video_dir / "chunk_1.mp4"
    vf.write_bytes(b"\x00\x00\x00\x1c" + b"ftypisom" + b"\x00" * 76)
    cursor.execute(
        """INSERT INTO video_chunks
           (file_path, device_name, status, monitor_id, start_time, end_time,
            checksum, app_name, window_name, monitor_width, monitor_height)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(vf), "cam0", "COMPLETED", "mon1",
         now - 120, now - 90, "sha_1", "TestApp", "TestWindow", 1920, 1080),
    )

    # Frame
    cursor.execute(
        """INSERT INTO frames
           (video_chunk_id, offset_index, timestamp, app_name, window_name, focused, browser_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (1, 0, now - 100, "TestApp", "TestWindow", 1, None),
    )
    frame_id = cursor.lastrowid
    (frames_dir / f"{frame_id}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def video_client(flask_app):
    """Client with seeded video data."""
    from openrecall.shared.config import settings
    _seed_video_data(settings.db_path, settings.video_chunks_path, settings.frames_path)
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def empty_video_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ===========================================================================
# Video Page Tests
# ===========================================================================

class TestVideoPage:

    def test_video_route_returns_200(self, video_client):
        resp = video_client.get("/video")
        assert resp.status_code == 200

    def test_video_page_extends_layout(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert "<header>" in html
        assert "MyRecall" in html

    def test_video_page_has_alpine_component(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert "videoDashboard()" in html
        assert "x-data" in html

    def test_video_page_has_stats_injection(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert 'id="initialVideoStats"' in html
        assert "application/json" in html

    def test_video_page_empty_state(self, empty_video_client):
        resp = empty_video_client.get("/video")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "No video data yet" in html

    def test_video_page_has_chunk_table(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert "data-table" in html
        assert "Monitor" in html

    def test_video_page_has_video_player(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert "<video" in html
        assert "controls" in html
        assert 'preload="metadata"' in html

    def test_video_page_has_frame_gallery(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert "frame-gallery" in html
        assert "frame-card" in html

    def test_video_page_guards_collapsed_chunk_during_async_frame_fetch(self, video_client):
        resp = video_client.get("/video")
        html = resp.data.decode()
        assert "if (!this.expandedChunks[chunkId]) return;" in html
        assert "if (this.expandedChunks[chunkId]) {" in html
