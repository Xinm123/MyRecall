"""Phase 2.6 smoke tests: audio hard-shutdown end-to-end behavior."""

import io
import json
import time
import wave

import numpy as np


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


class TestPhase26HardShutdownSmoke:
    """Smoke validations for the hard-shutdown contract."""

    def test_audio_upload_rejected_and_timeline_excludes_audio(self, flask_app, flask_client):
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        # 1) Upload audio chunk via v1 -> must be rejected
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": int(ts),
            "device_name": "smoke_mic",
            "checksum": "sha256:smoke_test_001",
        }
        resp = flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "smoke.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "AUDIO_HARD_SHUTDOWN"

        # 2) Seed historical audio data directly to verify retrieval remains audio-free.
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/phase26_smoke.wav",
            timestamp=ts,
            device_name="seeded_mic",
        )
        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=ts,
            transcription="phase2_smoke_audio_should_not_be_retrieved",
        )

        # 3) Timeline default path must not return audio.
        resp = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}"
        )
        assert resp.status_code == 200
        timeline_data = resp.get_json()
        assert all(item.get("type") != "audio_transcription" for item in timeline_data["data"])

        # 4) Explicit audio source request must return empty page.
        resp = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}&source=audio"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == []

        # 5) Queue status still exposes audio_queue for audit.
        resp = flask_client.get("/api/v1/queue/status")
        assert resp.status_code == 200
        queue_data = resp.get_json()
        assert "audio_queue" in queue_data

    def test_legacy_audio_upload_is_rejected(self, flask_client):
        wav_data = _make_wav_bytes(duration_s=0.5)
        metadata = {
            "type": "audio_chunk",
            "timestamp": int(time.time()),
            "device_name": "legacy_mic",
        }

        resp = flask_client.post(
            "/api/upload",
            data={
                "file": (io.BytesIO(wav_data), "legacy.wav", "audio/wav"),
                "metadata": json.dumps(metadata),
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 403
        assert resp.get_json()["code"] == "AUDIO_HARD_SHUTDOWN"

    def test_search_filters_out_audio_candidates(self, flask_client, monkeypatch):
        import openrecall.server.api_v1 as api_v1

        class _FakeSearchEngine:
            def search(self, _q, limit=50):
                return [
                    {
                        "source": "audio_transcription",
                        "audio_data": {
                            "id": 101,
                            "timestamp": 1700000000.0,
                            "device_name": "mic",
                            "transcription": "secret audio",
                            "snippet": "secret audio",
                        },
                    },
                    {
                        "source": "video_frame",
                        "video_data": {
                            "frame_id": 22,
                            "timestamp": 1700000001.0,
                            "app_name": "Chrome",
                            "window_name": "Docs",
                            "text_snippet": "vision hit",
                            "focused": 1,
                            "browser_url": "https://example.com",
                        },
                    },
                ][:limit]

        monkeypatch.setattr(api_v1, "_get_search_engine", lambda: _FakeSearchEngine())

        resp = flask_client.get("/api/v1/search?q=secret")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert all(item.get("scene_tag") != "audio_transcription" for item in data)
        assert any(item.get("scene_tag") == "video_frame" for item in data)
