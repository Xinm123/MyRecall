"""Phase 2.6 hard-shutdown gate tests (short-window contract checks)."""

import importlib
import io
import json
import time
import wave

import numpy as np


def _make_wav_bytes(duration_s: float = 0.5, sr: int = 16000) -> bytes:
    n_samples = int(sr * duration_s)
    audio = np.zeros(n_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def test_audio_enabled_is_forced_off_by_config(monkeypatch):
    monkeypatch.setenv("OPENRECALL_AUDIO_ENABLED", "true")
    import openrecall.shared.config as cfg

    importlib.reload(cfg)
    assert cfg.settings.audio_enabled is False


class TestHardShutdownContracts:
    def test_v1_upload_rejects_audio_payload(self, flask_client):
        wav_data = _make_wav_bytes()
        response = flask_client.post(
            "/api/v1/upload",
            data={
                "file": (io.BytesIO(wav_data), "gate26.wav", "audio/wav"),
                "metadata": json.dumps({
                    "type": "audio_chunk",
                    "timestamp": int(time.time()),
                    "device_name": "gate_mic",
                }),
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 403
        payload = response.get_json()
        assert payload["code"] == "AUDIO_HARD_SHUTDOWN"

    def test_legacy_upload_rejects_audio_payload(self, flask_client):
        wav_data = _make_wav_bytes()
        response = flask_client.post(
            "/api/upload",
            data={
                "file": (io.BytesIO(wav_data), "gate26_legacy.wav", "audio/wav"),
                "metadata": json.dumps({"type": "audio_chunk", "timestamp": int(time.time())}),
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 403
        payload = response.get_json()
        assert payload["code"] == "AUDIO_HARD_SHUTDOWN"

    def test_timeline_audio_source_returns_empty(self, flask_app, flask_client):
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/phase26_gate.wav",
            timestamp=ts,
            device_name="gate_mic",
        )
        sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=ts,
            transcription="must not be returned in timeline",
        )

        response = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}&source=audio"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []
        assert data["meta"]["total"] == 0

    def test_primary_navigation_has_no_audio_entry(self, flask_client):
        response = flask_client.get("/")
        assert response.status_code == 200
        html = response.data.decode()
        assert 'href="/audio"' not in html

    def test_search_api_drops_audio_results(self, flask_client, monkeypatch):
        import openrecall.server.api_v1 as api_v1

        class _FakeSearchEngine:
            def search(self, _q, limit=50):
                return [
                    {
                        "source": "audio_transcription",
                        "audio_data": {
                            "id": 8,
                            "timestamp": 1700000000.0,
                            "device_name": "mic",
                            "transcription": "hidden audio",
                            "snippet": "hidden audio",
                        },
                    }
                ][:limit]

        monkeypatch.setattr(api_v1, "_get_search_engine", lambda: _FakeSearchEngine())

        response = flask_client.get("/api/v1/search?q=hidden")
        assert response.status_code == 200
        data = response.get_json()
        assert data["data"] == []
