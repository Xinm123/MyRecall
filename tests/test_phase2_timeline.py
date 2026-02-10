"""Phase 2 tests: Unified timeline (video frames + audio transcriptions)."""

import io
import json
import sqlite3
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_wav_bytes(duration_s: float = 0.5, sr: int = 16000) -> bytes:
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


class TestTimelineAPI:
    """Tests for GET /api/v1/timeline unified endpoint."""

    def test_timeline_endpoint_exists(self, flask_client):
        """Timeline endpoint should be accessible."""
        now = time.time()
        response = flask_client.get(
            f"/api/v1/timeline?start_time={now - 3600}&end_time={now}"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data
        assert "meta" in data

    def test_timeline_empty_range(self, flask_client):
        """Timeline with no data should return empty."""
        response = flask_client.get(
            "/api/v1/timeline?start_time=0&end_time=1"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []

    def test_timeline_with_audio_transcriptions(self, flask_app, flask_client):
        """Timeline should include audio transcriptions."""
        from openrecall.shared.config import settings
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/timeline_audio.wav",
            timestamp=ts,
            device_name="mic",
        )

        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=ts,
            transcription="Timeline test audio",
        )

        response = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}"
        )
        assert response.status_code == 200
        data = response.get_json()

        audio_items = [d for d in data["data"] if d.get("type") == "audio_transcription"]
        assert len(audio_items) >= 1

    def test_timeline_source_filter_audio(self, flask_app, flask_client):
        """Source filter 'audio' should return only audio items."""
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/timeline_filter.wav",
            timestamp=ts,
            device_name="mic",
        )

        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=ts,
            transcription="Filter test audio",
        )

        response = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}&source=audio"
        )
        assert response.status_code == 200
        data = response.get_json()

        for item in data["data"]:
            assert item.get("type") == "audio_transcription"

    def test_timeline_source_filter_video(self, flask_client):
        """Source filter 'video' should exclude audio items."""
        now = time.time()
        response = flask_client.get(
            f"/api/v1/timeline?start_time={now - 3600}&end_time={now}&source=video"
        )
        assert response.status_code == 200

    def test_timeline_pagination(self, flask_app, flask_client):
        """Timeline should support pagination."""
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/timeline_page.wav",
            timestamp=ts,
            device_name="mic",
        )

        for i in range(5):
            sql_store.insert_audio_transcription(
                audio_chunk_id=chunk_id,
                offset_index=i,
                timestamp=ts + i,
                transcription=f"Pagination item {i}",
            )

        response = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}&limit=2&offset=0"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["data"]) <= 2
        assert data["meta"]["limit"] == 2

    def test_timeline_invalid_times(self, flask_client):
        """Invalid time params should return 400."""
        response = flask_client.get("/api/v1/timeline?start_time=not_a_number")
        assert response.status_code == 400


class TestAudioTranscriptionsAPI:
    """Tests for GET /api/v1/audio/transcriptions."""

    def test_transcriptions_endpoint_exists(self, flask_client):
        """Transcriptions endpoint should be accessible."""
        response = flask_client.get("/api/v1/audio/transcriptions")
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data

    def test_transcriptions_with_data(self, flask_app, flask_client):
        """Should return transcriptions within time range."""
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/trans_api.wav",
            timestamp=ts,
            device_name="api_mic",
        )

        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=ts,
            transcription="API test transcription",
        )

        response = flask_client.get(
            f"/api/v1/audio/transcriptions?start_time={ts - 60}&end_time={ts + 60}"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["meta"]["total"] >= 1
