"""Phase 2.6 tests: timeline retrieval contract is vision-only."""

import time


class TestTimelineAPI:
    """Tests for GET /api/v1/timeline under hard-shutdown contract."""

    def test_timeline_endpoint_exists(self, flask_client):
        now = time.time()
        response = flask_client.get(
            f"/api/v1/timeline?start_time={now - 3600}&end_time={now}"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data
        assert "meta" in data

    def test_timeline_empty_range(self, flask_client):
        response = flask_client.get(
            "/api/v1/timeline?start_time=0&end_time=1"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []

    def test_timeline_excludes_audio_transcriptions(self, flask_app, flask_client):
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
        assert audio_items == []

    def test_timeline_source_filter_audio_returns_empty(self, flask_app, flask_client):
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
        assert data["data"] == []
        assert data["meta"]["total"] == 0

    def test_timeline_source_filter_video(self, flask_client):
        now = time.time()
        response = flask_client.get(
            f"/api/v1/timeline?start_time={now - 3600}&end_time={now}&source=video"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert all(item.get("type") == "video_frame" for item in data["data"])

    def test_timeline_pagination(self, flask_client):
        now = time.time()
        response = flask_client.get(
            f"/api/v1/timeline?start_time={now - 3600}&end_time={now}&limit=2&offset=0"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["data"]) <= 2
        assert data["meta"]["limit"] == 2

    def test_timeline_invalid_times(self, flask_client):
        response = flask_client.get("/api/v1/timeline?start_time=not_a_number")
        assert response.status_code == 400


class TestAudioTranscriptionsAPI:
    """Audit endpoint remains available for historical inspection."""

    def test_transcriptions_endpoint_exists(self, flask_client):
        response = flask_client.get("/api/v1/audio/transcriptions")
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data

    def test_transcriptions_with_data(self, flask_app, flask_client):
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
