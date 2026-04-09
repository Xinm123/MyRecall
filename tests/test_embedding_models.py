"""Tests for embedding models."""
import pytest
from openrecall.server.embedding.models import FrameEmbedding


class TestFrameEmbedding:
    def test_frame_embedding_creation(self):
        emb = FrameEmbedding(
            frame_id=123,
            embedding_vector=[0.1] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="Chrome",
            window_name="GitHub",
        )
        assert emb.frame_id == 123
        assert emb.embedding_model == "qwen3-vl-embedding"
        assert emb.app_name == "Chrome"
        assert emb.window_name == "GitHub"

    def test_frame_embedding_defaults(self):
        emb = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.0] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        assert emb.app_name == ""
        assert emb.window_name == ""
        assert emb.embedding_model == "qwen3-vl-embedding"

    def test_frame_embedding_to_dict(self):
        emb = FrameEmbedding(
            frame_id=42,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="VSCode",
        )
        d = emb.to_storage_dict()
        assert d["frame_id"] == 42
        assert d["app_name"] == "VSCode"
