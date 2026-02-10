"""Phase 2 tests: Audio upload API + DB insertion."""

import io
import json
import wave
import sqlite3
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


def _make_wav_bytes(duration_s: float = 1.0, sr: int = 16000) -> bytes:
    """Create WAV file bytes in memory."""
    n_samples = int(sr * duration_s)
    audio = np.zeros(n_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class TestAudioUploadAPI:
    """Tests for /api/v1/upload with audio chunks."""

    def test_audio_upload_accepted(self, flask_client, tmp_path):
        """POST audio chunk should return 202 accepted."""
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": 1700000000,
            "device_name": "test_mic",
            "checksum": "sha256:abc123",
        }

        response = flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "test.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 202
        data = response.get_json()
        assert data["status"] == "accepted"
        assert "chunk_id" in data

    def test_audio_upload_creates_db_entry(self, flask_app, flask_client, tmp_path):
        """Upload should create a PENDING entry in audio_chunks table."""
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": 1700000001,
            "device_name": "test_mic",
            "checksum": "sha256:def456",
        }

        response = flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "test.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 202
        chunk_id = response.get_json()["chunk_id"]

        # Verify in database
        from openrecall.shared.config import settings

        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM audio_chunks WHERE id=?", (chunk_id,)
            ).fetchone()
            assert row is not None
            assert row["status"] == "PENDING"
            assert row["device_name"] == "test_mic"

    def test_audio_upload_by_content_type(self, flask_client):
        """Audio detection should work via content_type."""
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "timestamp": 1700000002,
            "device_name": "mic",
        }

        response = flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "chunk.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 202
        data = response.get_json()
        assert data["status"] == "accepted"

    def test_audio_upload_by_filename(self, flask_client):
        """Audio detection should work via .wav extension."""
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "timestamp": 1700000003,
            "device_name": "mic",
        }

        response = flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "audio_chunk.wav", "application/octet-stream"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 202

    def test_upload_no_file_returns_400(self, flask_client):
        """Missing file should return 400."""
        response = flask_client.post(
            "/api/v1/upload",
            data={"metadata": json.dumps({"timestamp": 0})},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400

    def test_upload_no_metadata_returns_400(self, flask_client):
        """Missing metadata should return 400."""
        wav_data = _make_wav_bytes(duration_s=0.1)
        response = flask_client.post(
            "/api/v1/upload",
            data={"file": (io.BytesIO(wav_data), "test.wav", "audio/wav")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400


class TestAudioChunksListAPI:
    """Tests for GET /api/v1/audio/chunks."""

    def test_list_audio_chunks_empty(self, flask_client):
        """Should return empty list when no chunks."""
        response = flask_client.get("/api/v1/audio/chunks")
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []

    def test_list_audio_chunks_after_upload(self, flask_client):
        """Should list uploaded chunks."""
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": 1700000010,
            "device_name": "mic",
            "checksum": "sha256:list_test",
        }

        flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "test.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        response = flask_client.get("/api/v1/audio/chunks")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["data"]) >= 1

    def test_list_audio_chunks_status_filter(self, flask_client):
        """Should filter by status."""
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": 1700000011,
            "device_name": "mic",
            "checksum": "sha256:filter_test",
        }

        flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "test.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        response = flask_client.get("/api/v1/audio/chunks?status=PENDING")
        assert response.status_code == 200
        data = response.get_json()
        assert all(c["status"] == "PENDING" for c in data["data"])


class TestQueueStatusAudio:
    """Tests for audio queue status in /api/v1/queue/status."""

    def test_queue_status_includes_audio(self, flask_client):
        """Queue status should have audio_queue section."""
        response = flask_client.get("/api/v1/queue/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "audio_queue" in data
        assert "pending" in data["audio_queue"]
