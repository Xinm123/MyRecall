"""Phase 2.5 Audio Page tests — /audio route returns 200, Alpine component, stats injection, etc.

Tests cover:
- GET /audio returns 200
- Page extends layout (has header, toolbar)
- Audio Alpine component present (audioDashboard)
- SSR stats injection (initialAudioStats)
- Empty state rendering
- Chunk table structure
- Audio player element
- Error banner element
"""

import json
import sqlite3
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_audio_data(db_path: Path, audio_dir: Path):
    """Seed minimal audio data for page rendering tests."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    for k, (status, device) in enumerate([
        ("COMPLETED", "microphone"),
        ("PENDING", "system_audio"),
    ], start=1):
        af = audio_dir / f"audio_{k}.wav"
        af.write_bytes(b"RIFF" + b"\x00" * 40)
        cursor.execute(
            """INSERT INTO audio_chunks
               (file_path, timestamp, device_name, status, checksum)
               VALUES (?, ?, ?, ?, ?)""",
            (str(af), now - 60 + k * 10, device, status, f"audio_sha_{k}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def audio_client(flask_app):
    """Client with seeded audio data."""
    from openrecall.shared.config import settings
    _seed_audio_data(settings.db_path, settings.server_audio_path)
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def empty_audio_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ===========================================================================
# Audio Page Tests
# ===========================================================================

class TestAudioPage:

    def test_audio_route_returns_200(self, audio_client):
        resp = audio_client.get("/audio")
        assert resp.status_code == 200

    def test_audio_page_extends_layout(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        # Layout header present
        assert "<header>" in html
        assert "MyRecall" in html

    def test_audio_page_has_alpine_component(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "audioDashboard()" in html
        assert "x-data" in html

    def test_audio_page_has_stats_injection(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert 'id="initialAudioStats"' in html
        assert "application/json" in html

    def test_audio_page_empty_state(self, empty_audio_client):
        resp = empty_audio_client.get("/audio")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Empty state message present in template
        assert "No audio data yet" in html

    def test_audio_page_has_chunk_table(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "data-table" in html
        assert "Device" in html

    def test_audio_page_has_audio_player(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "<audio" in html
        assert "<audio controls" not in html
        assert 'preload="metadata"' in html

    def test_audio_page_transcriptions_fetch_is_not_fixed_to_first_page(self, audio_client):
        """Client script should not lock transcriptions fetch to offset=0 only."""
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "audio/transcriptions?limit=${this.transLimit}&offset=0" not in html
        assert "meta?.has_more" in html

    def test_audio_page_has_error_banner(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "error-banner" in html

    def test_audio_page_has_filter_controls(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "audio-filters" in html
        assert "source-filter" in html
        assert "time-range" in html

    def test_audio_page_has_marker_rail(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "audio-marker-rail" in html
        assert "transcription-marker" in html

    def test_audio_page_has_thread_view(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "thread-view" in html
        assert "transcription-thread-list" in html

    def test_audio_page_no_longer_splits_chunks_and_transcriptions_tabs(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "tab-bar" not in html
        assert "activeTab" not in html

    def test_audio_page_renders_transcriptions_under_chunk(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert "chunk-transcriptions" in html
        assert "chunk-transcription-item" in html

    def test_audio_page_chunk_loop_does_not_use_nested_plain_template(self, audio_client):
        resp = audio_client.get("/audio")
        html = resp.data.decode()
        assert 'x-for="chunk in chunks"' in html
        assert '<template x-for="chunk in chunks" :key="chunk.id">\n            <template>' not in html
