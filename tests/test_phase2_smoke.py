"""Phase 2 Smoke Tests: End-to-end audio pipeline validation.

Chains the full audio flow: upload -> DB insert -> FTS index -> search -> timeline -> list endpoints.
"""

import io
import json
import time
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


class TestPhase2SmokeEndToEnd:
    """End-to-end smoke test chaining upload -> transcription -> search -> timeline."""

    def test_full_audio_pipeline(self, flask_app, flask_client):
        """Upload audio, insert transcription+FTS, search, timeline, list endpoints."""
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()
        phrase = "phase2_smoke_test_unique_phrase"

        # 1. Upload audio chunk via API
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
        assert resp.status_code == 202, f"Upload failed: {resp.get_json()}"
        chunk_id = resp.get_json()["chunk_id"]
        assert isinstance(chunk_id, int)

        # 2. Simulate processing: insert transcription + FTS (normally done by worker)
        trans_id = sql_store.insert_audio_transcription(
            audio_chunk_id=chunk_id,
            offset_index=0,
            timestamp=ts,
            transcription=phrase,
        )
        assert trans_id > 0

        sql_store.insert_audio_transcription_fts(
            transcription=phrase,
            device="smoke_mic",
            audio_chunk_id=chunk_id,
            speaker_id=None,
        )

        # Mark completed via direct SQL (worker methods use conn parameter)
        import sqlite3 as _sqlite3
        from openrecall.shared.config import settings
        with _sqlite3.connect(str(settings.db_path)) as conn:
            conn.execute(
                "UPDATE audio_chunks SET status='COMPLETED' WHERE id=?",
                (chunk_id,),
            )

        # 3. Verify audio chunks list endpoint
        resp = flask_client.get("/api/v1/audio/chunks")
        assert resp.status_code == 200
        chunks_data = resp.get_json()
        assert any(c["id"] == chunk_id for c in chunks_data["data"])

        # 4. Verify audio transcriptions endpoint
        resp = flask_client.get(
            f"/api/v1/audio/transcriptions?start_time={ts - 60}&end_time={ts + 60}"
        )
        assert resp.status_code == 200
        trans_data = resp.get_json()
        assert trans_data["meta"]["total"] >= 1

        # 5. Verify timeline includes audio transcription
        resp = flask_client.get(
            f"/api/v1/timeline?start_time={ts - 60}&end_time={ts + 60}"
        )
        assert resp.status_code == 200
        timeline_data = resp.get_json()
        audio_items = [
            d for d in timeline_data["data"]
            if d.get("type") == "audio_transcription"
        ]
        assert len(audio_items) >= 1

        # 6. Verify FTS search returns the transcription
        fts_results = sql_store.search_audio_fts(phrase, limit=10)
        assert len(fts_results) >= 1
        # FTS returns snippet field with <b> tags
        assert any(
            phrase in r.get("snippet", "").replace("<b>", "").replace("</b>", "")
            for r in fts_results
        )

        # 7. Verify queue status includes audio_queue
        resp = flask_client.get("/api/v1/queue/status")
        assert resp.status_code == 200
        queue_data = resp.get_json()
        assert "audio_queue" in queue_data

    def test_audio_upload_then_chunks_status(self, flask_app, flask_client):
        """Upload multiple chunks and verify status filtering."""
        from openrecall.server.database import SQLStore

        sql_store = SQLStore()
        ts = time.time()

        # Upload two chunks
        for i in range(2):
            wav_data = _make_wav_bytes(duration_s=0.3)
            metadata = {
                "type": "audio_chunk",
                "timestamp": int(ts) + i,
                "device_name": "smoke_mic",
                "checksum": f"sha256:smoke_multi_{i}",
            }
            resp = flask_client.post(
                "/api/v1/upload",
                data={
                    "file": (io.BytesIO(wav_data), f"multi_{i}.wav", "audio/wav"),
                    "metadata": json.dumps(metadata),
                },
                content_type="multipart/form-data",
            )
            assert resp.status_code == 202

        # Both should be PENDING
        resp = flask_client.get("/api/v1/audio/chunks?status=PENDING")
        assert resp.status_code == 200
        pending = resp.get_json()["data"]
        assert len(pending) >= 2

        # No COMPLETED yet
        resp = flask_client.get("/api/v1/audio/chunks?status=COMPLETED")
        assert resp.status_code == 200
        completed = resp.get_json()["data"]
        assert len(completed) == 0
