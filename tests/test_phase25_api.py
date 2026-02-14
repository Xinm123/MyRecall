"""Phase 2.5 API tests — video/audio dashboard endpoints + file serving + path security.

Tests cover:
- GET /api/v1/video/chunks (pagination, filters)
- GET /api/v1/video/chunks/<id>/file (mp4 serving, 404, path security)
- GET /api/v1/video/frames (pagination, multi-filter, OCR snippet)
- GET /api/v1/video/stats (structure, values, empty db)
- GET /api/v1/audio/chunks/<id>/file (WAV serving, 404, path security)
- GET /api/v1/audio/stats (structure, values, empty db)
- GET /api/v1/audio/chunks?device= (additive device filter)
- Path traversal prevention (gate 2.5-DG-01)
"""

import io
import json
import os
import sqlite3
import struct
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav_bytes(duration_ms: int = 100, sample_rate: int = 16000) -> bytes:
    """Generate a minimal valid WAV file in memory."""
    num_samples = int(sample_rate * duration_ms / 1000)
    data_size = num_samples * 2  # 16-bit mono
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(b"\x00" * data_size)
    return buf.getvalue()


def _make_mp4_bytes() -> bytes:
    """Generate minimal bytes that look like an mp4 (enough for tests)."""
    return b"\x00\x00\x00\x1c" + b"ftypisom" + b"\x00" * 12 + b"\x00" * 64


def _seed_data(db_path: Path, video_dir: Path, audio_dir: Path, frames_dir: Path):
    """Seed database with test data for audio + video dashboard APIs."""
    video_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # --- Video chunks (3) ---
    video_files = []
    for i, (status, monitor) in enumerate([
        ("COMPLETED", "mon1"),
        ("PENDING", "mon1"),
        ("FAILED", "mon2"),
    ], start=1):
        vf = video_dir / f"chunk_{i}.mp4"
        vf.write_bytes(_make_mp4_bytes())
        video_files.append(vf)
        cursor.execute(
            """INSERT INTO video_chunks
               (file_path, device_name, status, monitor_id, start_time, end_time,
                checksum, app_name, window_name, monitor_width, monitor_height)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(vf), "cam0", status, monitor,
             now - 120 + i * 30, now - 90 + i * 30,
             f"sha_{i}", "TestApp", "TestWindow", 1920, 1080),
        )

    # --- Frames (5, all linked to video chunk 1) ---
    for j in range(1, 6):
        cursor.execute(
            """INSERT INTO frames
               (video_chunk_id, offset_index, timestamp, app_name, window_name, focused, browser_url)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (1, j - 1, now - 100 + j * 5, f"App{j}", f"Win{j}",
             1 if j % 2 == 0 else 0, f"https://example.com/{j}" if j <= 3 else None),
        )
        frame_id = cursor.lastrowid
        # OCR text for the frame
        cursor.execute(
            "INSERT INTO ocr_text (frame_id, text, ocr_engine) VALUES (?, ?, ?)",
            (frame_id, f"OCR text for frame {frame_id} " + "x" * 250, "test_ocr"),
        )
        # Create a dummy frame PNG file
        (frames_dir / f"{frame_id}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    # --- Audio chunks (3) ---
    for k, (status, device) in enumerate([
        ("COMPLETED", "microphone"),
        ("COMPLETED", "system_audio"),
        ("PENDING", "microphone"),
    ], start=1):
        af = audio_dir / f"audio_{k}.wav"
        af.write_bytes(_make_wav_bytes())
        cursor.execute(
            """INSERT INTO audio_chunks
               (file_path, timestamp, device_name, status, checksum)
               VALUES (?, ?, ?, ?, ?)""",
            (str(af), now - 60 + k * 10, device, status, f"audio_sha_{k}"),
        )

    # --- Audio transcriptions (2, linked to audio chunk 1) ---
    for m in range(1, 3):
        cursor.execute(
            """INSERT INTO audio_transcriptions
               (audio_chunk_id, offset_index, timestamp, transcription, transcription_engine)
               VALUES (?, ?, ?, ?, ?)""",
            (1, m - 1, now - 50 + m * 5, f"Transcription segment {m}", "test_whisper"),
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_with_data(flask_app, tmp_path):
    """Flask app with seeded audio/video test data."""
    from openrecall.shared.config import settings
    _seed_data(
        db_path=settings.db_path,
        video_dir=settings.video_chunks_path,
        audio_dir=settings.server_audio_path,
        frames_dir=settings.frames_path,
    )
    return flask_app


@pytest.fixture
def client(app_with_data):
    app_with_data.config["TESTING"] = True
    with app_with_data.test_client() as c:
        yield c


@pytest.fixture
def empty_client(flask_app):
    """Client with empty DB (no seeded data)."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ===========================================================================
# Video Chunks API
# ===========================================================================

class TestVideoChunksAPI:

    def test_list_video_chunks_returns_paginated(self, client):
        resp = client.get("/api/v1/video/chunks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] == 3
        assert len(data["data"]) == 3

    def test_list_video_chunks_status_filter(self, client):
        resp = client.get("/api/v1/video/chunks?status=COMPLETED")
        data = resp.get_json()
        assert data["meta"]["total"] == 1
        assert data["data"][0]["status"] == "COMPLETED"

    def test_list_video_chunks_monitor_id_filter(self, client):
        resp = client.get("/api/v1/video/chunks?monitor_id=mon2")
        data = resp.get_json()
        assert data["meta"]["total"] == 1
        assert data["data"][0]["monitor_id"] == "mon2"

    def test_list_video_chunks_pagination(self, client):
        resp = client.get("/api/v1/video/chunks?limit=2&offset=0")
        data = resp.get_json()
        assert len(data["data"]) == 2
        assert data["meta"]["has_more"] is True

        resp2 = client.get("/api/v1/video/chunks?limit=2&offset=2")
        data2 = resp2.get_json()
        assert len(data2["data"]) == 1
        assert data2["meta"]["has_more"] is False

    def test_list_video_chunks_page_size_alias(self, client):
        resp = client.get("/api/v1/video/chunks?page=1&page_size=2")
        data = resp.get_json()
        assert len(data["data"]) == 2
        assert data["meta"]["limit"] == 2
        assert data["meta"]["offset"] == 0

    def test_list_video_chunks_empty_db(self, empty_client):
        resp = empty_client.get("/api/v1/video/chunks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["total"] == 0
        assert data["data"] == []


# ===========================================================================
# Video Chunk File Serving
# ===========================================================================

class TestVideoChunkFileAPI:

    def test_serve_video_chunk_file(self, client):
        resp = client.get("/api/v1/video/chunks/1/file")
        assert resp.status_code == 200
        assert resp.content_type == "video/mp4"
        assert len(resp.data) > 0

    def test_serve_nonexistent_chunk_404(self, client):
        resp = client.get("/api/v1/video/chunks/999/file")
        assert resp.status_code == 404

    def test_serve_missing_file_404(self, client, tmp_path):
        """If the DB record exists but the file was deleted from disk."""
        from openrecall.shared.config import settings
        # Delete file #2 from disk
        conn = sqlite3.connect(str(settings.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM video_chunks WHERE id=2")
        fp = cursor.fetchone()[0]
        conn.close()
        Path(fp).unlink(missing_ok=True)

        resp = client.get("/api/v1/video/chunks/2/file")
        assert resp.status_code == 404

    def test_path_traversal_blocked_403(self, client, tmp_path):
        """Inject a path outside video_chunks_path — must get 403."""
        from openrecall.shared.config import settings
        evil_file = tmp_path / "evil.mp4"
        evil_file.write_bytes(_make_mp4_bytes())
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE video_chunks SET file_path=? WHERE id=1",
            (str(evil_file),),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/video/chunks/1/file")
        assert resp.status_code == 403


# ===========================================================================
# Video Frames API
# ===========================================================================

class TestVideoFramesAPI:

    def test_list_frames_paginated(self, client):
        resp = client.get("/api/v1/video/frames")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["total"] == 5

    def test_list_frames_chunk_id_filter(self, client):
        resp = client.get("/api/v1/video/frames?chunk_id=1")
        data = resp.get_json()
        assert data["meta"]["total"] == 5

        resp2 = client.get("/api/v1/video/frames?chunk_id=999")
        data2 = resp2.get_json()
        assert data2["meta"]["total"] == 0

    def test_list_frames_time_range_filter(self, client):
        resp = client.get("/api/v1/video/frames?start_time=0&end_time=9999999999")
        data = resp.get_json()
        assert data["meta"]["total"] == 5

    def test_list_frames_includes_ocr_snippet(self, client):
        resp = client.get("/api/v1/video/frames?limit=1")
        data = resp.get_json()
        frame = data["data"][0]
        assert "ocr_snippet" in frame
        # OCR snippet should be truncated to 200 chars
        assert len(frame["ocr_snippet"]) <= 200
        assert "frame_url" in frame
        assert frame["frame_url"].startswith("/api/v1/frames/")

    def test_list_frames_empty_db(self, empty_client):
        resp = empty_client.get("/api/v1/video/frames")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["total"] == 0


# ===========================================================================
# Video Stats API
# ===========================================================================

class TestVideoStatsAPI:

    def test_video_stats_structure(self, client):
        resp = client.get("/api/v1/video/stats")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "total_chunks" in data
        assert "total_frames" in data
        assert "total_duration_seconds" in data
        assert "storage_bytes" in data
        assert "status_counts" in data

    def test_video_stats_values(self, client):
        data = client.get("/api/v1/video/stats").get_json()["data"]
        assert data["total_chunks"] == 3
        assert data["total_frames"] == 5
        assert data["storage_bytes"] > 0
        assert isinstance(data["status_counts"], dict)

    def test_video_stats_empty_db(self, empty_client):
        data = empty_client.get("/api/v1/video/stats").get_json()["data"]
        assert data["total_chunks"] == 0
        assert data["total_frames"] == 0


# ===========================================================================
# Audio Chunk File Serving
# ===========================================================================

class TestAudioChunkFileAPI:

    def test_serve_audio_chunk_file(self, client):
        resp = client.get("/api/v1/audio/chunks/1/file")
        assert resp.status_code == 200
        assert resp.content_type == "audio/wav"
        assert len(resp.data) > 0

    def test_serve_nonexistent_chunk_404(self, client):
        resp = client.get("/api/v1/audio/chunks/999/file")
        assert resp.status_code == 404

    def test_serve_missing_file_404(self, client):
        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM audio_chunks WHERE id=3")
        fp = cursor.fetchone()[0]
        conn.close()
        Path(fp).unlink(missing_ok=True)

        resp = client.get("/api/v1/audio/chunks/3/file")
        assert resp.status_code == 404

    def test_path_traversal_blocked_403(self, client, tmp_path):
        """Inject a path outside server_audio_path — must get 403."""
        from openrecall.shared.config import settings
        evil_file = tmp_path / "evil.wav"
        evil_file.write_bytes(_make_wav_bytes())
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE audio_chunks SET file_path=? WHERE id=1",
            (str(evil_file),),
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/audio/chunks/1/file")
        assert resp.status_code == 403


# ===========================================================================
# Audio Stats API
# ===========================================================================

class TestAudioStatsAPI:

    def test_audio_stats_structure(self, client):
        resp = client.get("/api/v1/audio/stats")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "total_chunks" in data
        assert "total_transcriptions" in data
        assert "total_duration_seconds" in data
        assert "storage_bytes" in data
        assert "status_counts" in data
        assert "device_counts" in data

    def test_audio_stats_values(self, client):
        data = client.get("/api/v1/audio/stats").get_json()["data"]
        assert data["total_chunks"] == 3
        assert data["total_transcriptions"] == 2
        assert data["storage_bytes"] > 0
        assert isinstance(data["device_counts"], dict)

    def test_audio_stats_empty_db(self, empty_client):
        data = empty_client.get("/api/v1/audio/stats").get_json()["data"]
        assert data["total_chunks"] == 0
        assert data["total_transcriptions"] == 0

    def test_audio_stats_include_source_counts(self, client):
        data = client.get("/api/v1/audio/stats").get_json()["data"]
        assert "source_counts" in data
        assert isinstance(data["source_counts"], dict)

    def test_audio_stats_duration_aggregates_chunk_timing(self, client):
        from openrecall.shared.config import settings

        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE audio_chunks SET start_time=timestamp-2.5, end_time=timestamp WHERE id IN (1, 2, 3)"
        )
        conn.commit()
        conn.close()

        data = client.get("/api/v1/audio/stats").get_json()["data"]
        assert data["total_duration_seconds"] == pytest.approx(7.5, rel=0.01)


# ===========================================================================
# Audio Chunks Device Filter (additive, no breaking change)
# ===========================================================================

class TestAudioChunksDeviceFilter:

    def test_device_filter_returns_matching(self, client):
        resp = client.get("/api/v1/audio/chunks?device=microphone")
        data = resp.get_json()
        assert data["meta"]["total"] == 2
        for chunk in data["data"]:
            assert chunk["device_name"] == "microphone"

    def test_device_filter_no_match_returns_empty(self, client):
        resp = client.get("/api/v1/audio/chunks?device=nonexistent")
        data = resp.get_json()
        assert data["meta"]["total"] == 0

    def test_no_device_returns_all(self, client):
        resp = client.get("/api/v1/audio/chunks")
        data = resp.get_json()
        assert data["meta"]["total"] == 3


class TestAudioChunksSourceAndShape:

    def test_source_filter_returns_only_input_rows(self, client):
        from openrecall.shared.config import settings

        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE audio_chunks SET source_kind='input', is_input=1, start_time=timestamp-2, end_time=timestamp WHERE id IN (1, 3)"
        )
        conn.execute(
            "UPDATE audio_chunks SET source_kind='output', is_input=0, start_time=timestamp-2, end_time=timestamp WHERE id=2"
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/audio/chunks?source=input")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["meta"]["total"] == 2
        for chunk in payload["data"]:
            assert chunk["source_kind"] == "input"
            assert chunk["is_input"] in (1, True)

    def test_audio_chunks_include_transcription_count_fields(self, client):
        from openrecall.shared.config import settings

        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE audio_chunks SET source_kind='input', is_input=1, start_time=timestamp-2, end_time=timestamp WHERE id=1"
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/audio/chunks?limit=1")
        assert resp.status_code == 200
        row = resp.get_json()["data"][0]
        assert "source_kind" in row
        assert "is_input" in row
        assert "start_time" in row
        assert "end_time" in row
        assert "transcriptions_count" in row
        assert "latest_transcription_at" in row


class TestAudioTranscriptionsSourceAndShape:

    def test_transcriptions_support_source_filter_and_file_url(self, client):
        from openrecall.shared.config import settings

        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE audio_chunks SET source_kind='input', is_input=1, start_time=timestamp-2, end_time=timestamp WHERE id=1"
        )
        conn.execute(
            "UPDATE audio_chunks SET source_kind='output', is_input=0, start_time=timestamp-2, end_time=timestamp WHERE id=2"
        )
        conn.commit()
        conn.close()

        resp = client.get("/api/v1/audio/transcriptions?source=input&sort=asc")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["meta"]["total"] >= 1
        for row in payload["data"]:
            assert row["source_kind"] == "input"
            assert row["is_input"] in (1, True)
            assert row["audio_file_url"].startswith("/api/v1/audio/chunks/")


# ===========================================================================
# File Serving Path Security (GATING gate 2.5-DG-01)
# ===========================================================================

class TestFileServingPathSecurity:

    def test_video_dotdot_traversal(self, client, tmp_path):
        """Path with .. components must be blocked."""
        from openrecall.shared.config import settings
        # Create a file outside video dir using ..
        parent = settings.video_chunks_path.parent
        evil = parent / "evil_vid.mp4"
        evil.write_bytes(_make_mp4_bytes())
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE video_chunks SET file_path=? WHERE id=1",
            (str(settings.video_chunks_path / ".." / "evil_vid.mp4"),),
        )
        conn.commit()
        conn.close()
        resp = client.get("/api/v1/video/chunks/1/file")
        assert resp.status_code == 403

    def test_audio_dotdot_traversal(self, client, tmp_path):
        from openrecall.shared.config import settings
        parent = settings.server_audio_path.parent
        evil = parent / "evil_aud.wav"
        evil.write_bytes(_make_wav_bytes())
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "UPDATE audio_chunks SET file_path=? WHERE id=1",
            (str(settings.server_audio_path / ".." / "evil_aud.wav"),),
        )
        conn.commit()
        conn.close()
        resp = client.get("/api/v1/audio/chunks/1/file")
        assert resp.status_code == 403
