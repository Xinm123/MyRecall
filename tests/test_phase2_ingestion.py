"""Phase 2.6 tests: audio hard-shutdown ingestion behavior."""

import io
import json
import sqlite3
import wave

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


class TestAudioUploadHardShutdown:
    """Audio payloads must be rejected in Phase 2.6."""

    def test_audio_upload_rejected_v1(self, flask_client):
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

        assert response.status_code == 403
        data = response.get_json()
        assert data["status"] == "error"
        assert data["code"] == "AUDIO_HARD_SHUTDOWN"

    def test_audio_upload_rejected_legacy_api(self, flask_client):
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": 1700000001,
            "device_name": "legacy_mic",
        }

        response = flask_client.post(
            "/api/upload",
            data={
                "file": (io.BytesIO(wav_data), "legacy.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data["status"] == "error"
        assert data["code"] == "AUDIO_HARD_SHUTDOWN"

    def test_audio_upload_rejected_does_not_create_db_entry(self, flask_client):
        from openrecall.shared.config import settings

        with sqlite3.connect(str(settings.db_path)) as conn:
            baseline = conn.execute("SELECT COUNT(*) FROM audio_chunks").fetchone()[0]

        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": 1700000002,
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
        assert response.status_code == 403

        with sqlite3.connect(str(settings.db_path)) as conn:
            final = conn.execute("SELECT COUNT(*) FROM audio_chunks").fetchone()[0]

        assert final == baseline

    def test_upload_no_file_returns_400(self, flask_client):
        response = flask_client.post(
            "/api/v1/upload",
            data={"metadata": json.dumps({"timestamp": 0})},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400

    def test_upload_no_metadata_returns_400(self, flask_client):
        wav_data = _make_wav_bytes(duration_s=0.1)
        response = flask_client.post(
            "/api/v1/upload",
            data={"file": (io.BytesIO(wav_data), "test.wav", "audio/wav")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400


class TestAudioAuditAPIs:
    """Audit-only audio endpoints remain readable."""

    def test_list_audio_chunks_empty(self, flask_client):
        response = flask_client.get("/api/v1/audio/chunks")
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []

    def test_audio_transcriptions_empty(self, flask_client):
        response = flask_client.get("/api/v1/audio/transcriptions")
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []

    def test_queue_status_includes_audio(self, flask_client):
        response = flask_client.get("/api/v1/queue/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "audio_queue" in data
        assert "pending" in data["audio_queue"]
