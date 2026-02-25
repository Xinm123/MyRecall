"""Phase 2 tests: Audio FTS search integration."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAudioFTSSearch:
    """Tests for audio transcription FTS search."""

    @pytest.fixture
    def sql_store(self, flask_app):
        from openrecall.server.database import SQLStore
        return SQLStore()

    def test_insert_and_search_transcription(self, sql_store):
        """Insert a transcription + FTS entry and verify search finds it."""
        # Insert audio chunk first
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/search_test.wav",
            timestamp=1700000000.0,
            device_name="test_mic",
        )
        assert chunk_id is not None

        # Insert transcription
        trans_id = sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=1700000000.0,
            transcription="The quick brown fox jumps over the lazy dog",
            transcription_engine="faster-whisper:base",
        )
        assert trans_id is not None

        # Insert FTS
        sql_store.insert_audio_transcription_fts(
            transcription="The quick brown fox jumps over the lazy dog",
            device="test_mic",
            audio_chunk_id=chunk_id,
        )

        # Search
        results = sql_store.search_audio_fts("brown fox", limit=10)
        assert len(results) >= 1
        assert any("brown" in str(r.get("snippet", r.get("transcription", ""))).lower() for r in results)

    def test_search_no_results(self, sql_store):
        """Search for nonexistent term should return empty."""
        results = sql_store.search_audio_fts("xyznonexistent123", limit=10)
        assert results == []

    def test_search_audio_fts_pagination(self, sql_store):
        """Search should respect limit."""
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/fts_page.wav",
            timestamp=1700000100.0,
            device_name="mic",
        )

        for i in range(5):
            sql_store.insert_audio_transcription(
                audio_chunk_id=chunk_id,
                offset_index=i,
                timestamp=1700000100.0 + i,
                transcription=f"unique_pagination_term number {i}",
            )
            sql_store.insert_audio_transcription_fts(
                transcription=f"unique_pagination_term number {i}",
                device="mic",
                audio_chunk_id=chunk_id,
            )

        results = sql_store.search_audio_fts("unique_pagination_term", limit=3)
        assert len(results) <= 3

    def test_get_audio_transcriptions_by_time_range(self, sql_store):
        """Time range query should return matching transcriptions."""
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/range_test.wav",
            timestamp=1700000200.0,
            device_name="mic",
        )

        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=1700000200.0,
            transcription="Range test transcription",
        )

        transcriptions, total = sql_store.get_audio_transcriptions_by_time_range(
            start_time=1700000000.0,
            end_time=1700000300.0,
        )
        assert total >= 1
        assert any("Range test" in t["transcription"] for t in transcriptions)

    def test_get_audio_transcriptions_outside_range(self, sql_store):
        """Queries outside time range should return empty."""
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/outside.wav",
            timestamp=1700000400.0,
        )

        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=1700000400.0,
            transcription="Outside range text",
        )

        transcriptions, total = sql_store.get_audio_transcriptions_by_time_range(
            start_time=1600000000.0,
            end_time=1600000100.0,
        )
        assert total == 0


class TestSearchAPIAudio:
    """Tests for /api/v1/search audio hard-shutdown behavior."""

    def test_search_endpoint_exists(self, flask_client):
        """Search endpoint should be accessible."""
        response = flask_client.get("/api/v1/search?q=test")
        assert response.status_code == 200

    def test_search_empty_query(self, flask_client):
        """Empty query should return empty results."""
        response = flask_client.get("/api/v1/search?q=")
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []

    def test_search_filters_out_audio_candidates(self, flask_client, monkeypatch):
        """Audio candidates returned by engine must be dropped at API layer."""
        import openrecall.server.api_v1 as api_v1

        class _FakeSearchEngine:
            def search(self, _q, limit=50):
                return [
                    {
                        "source": "audio_transcription",
                        "audio_data": {
                            "id": 1,
                            "timestamp": 1700000000.0,
                            "device_name": "mic",
                            "transcription": "audio should be excluded",
                            "snippet": "audio should be excluded",
                        },
                    },
                    {
                        "source": "video_frame",
                        "video_data": {
                            "frame_id": 9,
                            "timestamp": 1700000001.0,
                            "app_name": "Chrome",
                            "window_name": "Docs",
                            "text_snippet": "video result",
                            "focused": 1,
                            "browser_url": "https://example.com",
                        },
                    },
                ][:limit]

        monkeypatch.setattr(api_v1, "_get_search_engine", lambda: _FakeSearchEngine())

        response = flask_client.get("/api/v1/search?q=excluded")
        assert response.status_code == 200
        data = response.get_json()
        assert all(item.get("scene_tag") != "audio_transcription" for item in data["data"])
        assert any(item.get("scene_tag") == "video_frame" for item in data["data"])
