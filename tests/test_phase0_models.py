"""Tests for Phase 0 Pydantic models."""

import pytest

from openrecall.shared.models import (
    AudioChunk,
    AudioTranscription,
    Frame,
    OcrText,
    PaginatedResponse,
    RecallEntry,
    VideoChunk,
)


class TestVideoChunk:
    def test_creation_with_defaults(self):
        vc = VideoChunk(file_path="/tmp/video.mp4")
        assert vc.file_path == "/tmp/video.mp4"
        assert vc.device_name == ""
        assert vc.encrypted == 0
        assert vc.checksum is None
        assert vc.expires_at is None
        assert vc.id is None

    def test_creation_with_all_fields(self):
        vc = VideoChunk(
            id=1,
            file_path="/tmp/video.mp4",
            device_name="screen0",
            created_at="2026-02-06 10:00:00",
            expires_at="2026-03-06 10:00:00",
            encrypted=1,
            checksum="abc123",
        )
        assert vc.id == 1
        assert vc.encrypted == 1
        assert vc.checksum == "abc123"


class TestFrame:
    def test_creation_with_required_fields(self):
        f = Frame(video_chunk_id=1, offset_index=0, timestamp=1000.0)
        assert f.video_chunk_id == 1
        assert f.offset_index == 0
        assert f.timestamp == 1000.0
        assert f.app_name == ""
        assert f.focused is False

    def test_creation_with_all_fields(self):
        f = Frame(
            id=5,
            video_chunk_id=1,
            offset_index=10,
            timestamp=1000.5,
            app_name="Chrome",
            window_name="GitHub",
            focused=True,
            browser_url="https://github.com",
        )
        assert f.focused is True
        assert f.browser_url == "https://github.com"


class TestOcrText:
    def test_creation(self):
        o = OcrText(frame_id=1, text="Hello world")
        assert o.frame_id == 1
        assert o.text == "Hello world"
        assert o.ocr_engine == ""
        assert o.text_length is None

    def test_with_optional_fields(self):
        o = OcrText(
            frame_id=1,
            text="Test",
            text_json='{"blocks":[]}',
            ocr_engine="doctr",
            text_length=4,
        )
        assert o.text_json == '{"blocks":[]}'
        assert o.text_length == 4


class TestAudioChunk:
    def test_creation_with_defaults(self):
        ac = AudioChunk(file_path="/tmp/audio.wav", timestamp=1000.0)
        assert ac.file_path == "/tmp/audio.wav"
        assert ac.timestamp == 1000.0
        assert ac.device_name == ""
        assert ac.encrypted == 0

    def test_creation_with_all_fields(self):
        ac = AudioChunk(
            id=1,
            file_path="/tmp/audio.wav",
            timestamp=1000.0,
            device_name="microphone",
            expires_at="2026-03-06",
            encrypted=1,
            checksum="sha256hash",
        )
        assert ac.encrypted == 1


class TestAudioTranscription:
    def test_nullable_speaker_id(self):
        """ADR-0004: speaker_id is None by default."""
        at = AudioTranscription(
            audio_chunk_id=1,
            offset_index=0,
            timestamp=1000.0,
            transcription="Hello world",
        )
        assert at.speaker_id is None
        assert at.transcription_engine == ""

    def test_with_speaker_id(self):
        at = AudioTranscription(
            audio_chunk_id=1,
            offset_index=0,
            timestamp=1000.0,
            transcription="Hello",
            speaker_id=42,
            start_time=0.0,
            end_time=1.5,
            text_length=5,
        )
        assert at.speaker_id == 42
        assert at.start_time == 0.0
        assert at.end_time == 1.5


class TestPaginatedResponse:
    def test_generic_with_video_chunk(self):
        items = [VideoChunk(file_path=f"/tmp/{i}.mp4") for i in range(3)]
        resp = PaginatedResponse[VideoChunk](
            items=items, total=10, limit=3, offset=0, has_more=True
        )
        assert len(resp.items) == 3
        assert resp.total == 10
        assert resp.has_more is True

    def test_has_more_false(self):
        resp = PaginatedResponse[VideoChunk](
            items=[], total=0, limit=10, offset=0, has_more=False
        )
        assert resp.has_more is False
        assert resp.total == 0

    def test_serialization(self):
        items = [VideoChunk(file_path="/tmp/test.mp4")]
        resp = PaginatedResponse[VideoChunk](
            items=items, total=1, limit=10, offset=0, has_more=False
        )
        data = resp.model_dump()
        assert data["total"] == 1
        assert data["items"][0]["file_path"] == "/tmp/test.mp4"


class TestRecallEntryUnchanged:
    def test_recall_entry_still_works(self):
        """Existing RecallEntry model is not broken by new additions."""
        entry = RecallEntry(timestamp=1000, app="Chrome")
        assert entry.timestamp == 1000
        assert entry.status == "PENDING"
        assert entry.embedding is None
