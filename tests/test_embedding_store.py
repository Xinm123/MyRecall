# tests/test_embedding_store.py
"""Tests for embedding store (LanceDB)."""
import tempfile
import shutil
from pathlib import Path

import pytest

from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.database.embedding_store import EmbeddingStore


class TestEmbeddingStore:
    def test_init_creates_table(self, tmp_path):
        """Store initialization should create the table."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))
        # Should not raise
        assert store.table_name == "frame_embeddings"

    def test_save_and_search_embedding(self, tmp_path):
        """Should save embedding and search by similarity."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        # Create embedding
        emb = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.1] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="Chrome",
            window_name="GitHub",
        )

        # Save
        store.save_embedding(emb)

        # Search with same vector
        results = store.search([0.1] * 1024, limit=5)

        assert len(results) == 1
        assert results[0].frame_id == 1

    def test_search_returns_multiple_results(self, tmp_path):
        """Search should return multiple results sorted by similarity."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        # Save two embeddings with different vectors
        emb1 = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.9] * 1024,  # High values
            timestamp="2026-04-09T12:00:00Z",
        )
        emb2 = FrameEmbedding(
            frame_id=2,
            embedding_vector=[0.1] * 1024,  # Low values
            timestamp="2026-04-09T12:01:00Z",
        )
        store.save_embedding(emb1)
        store.save_embedding(emb2)

        # Search with high-value vector should return emb1 first
        results = store.search([0.9] * 1024, limit=10)
        assert len(results) == 2
        assert results[0].frame_id == 1  # Higher similarity

    def test_get_embedding_by_frame_id(self, tmp_path):
        """Should retrieve embedding by frame_id."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        emb = FrameEmbedding(
            frame_id=42,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        store.save_embedding(emb)

        result = store.get_by_frame_id(42)
        assert result is not None
        assert result.frame_id == 42

    def test_get_embedding_not_found(self, tmp_path):
        """Should return None for non-existent frame_id."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))
        result = store.get_by_frame_id(999)
        assert result is None

    def test_delete_by_frame_id(self, tmp_path):
        """Should delete embedding by frame_id."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        emb = FrameEmbedding(
            frame_id=42,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        store.save_embedding(emb)

        # Verify it exists
        assert store.get_by_frame_id(42) is not None

        # Delete
        store.delete_by_frame_id(42)

        # Verify it's gone
        assert store.get_by_frame_id(42) is None

    def test_count(self, tmp_path):
        """Should return total count of embeddings."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        assert store.count() == 0

        emb1 = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.1] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        emb2 = FrameEmbedding(
            frame_id=2,
            embedding_vector=[0.2] * 1024,
            timestamp="2026-04-09T12:01:00Z",
        )

        store.save_embedding(emb1)
        assert store.count() == 1

        store.save_embedding(emb2)
        assert store.count() == 2

    def test_search_with_distance(self, tmp_path):
        """Should return embeddings with distance scores."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        emb = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        store.save_embedding(emb)

        results = store.search_with_distance([0.5] * 1024, limit=5)

        assert len(results) == 1
        result_emb, distance = results[0]
        assert result_emb.frame_id == 1
        assert isinstance(distance, float)

    def test_save_embedding_upsert(self, tmp_path):
        """Saving an embedding for existing frame_id should update it."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        # Save initial embedding
        emb1 = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.1] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="Initial",
        )
        store.save_embedding(emb1)

        # Save updated embedding for same frame_id
        emb2 = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.9] * 1024,
            timestamp="2026-04-09T12:01:00Z",
            app_name="Updated",
        )
        store.save_embedding(emb2)

        # Should have only one embedding
        assert store.count() == 1

        # Should have updated values
        result = store.get_by_frame_id(1)
        assert result is not None
        assert result.app_name == "Updated"

    def test_search_preserves_metadata(self, tmp_path):
        """Search results should include all metadata fields."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        emb = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="Chrome",
            window_name="GitHub - MyRecall",
        )
        store.save_embedding(emb)

        results = store.search([0.5] * 1024, limit=5)

        assert len(results) == 1
        result = results[0]
        assert result.frame_id == 1
        assert result.timestamp == "2026-04-09T12:00:00Z"
        assert result.app_name == "Chrome"
        assert result.window_name == "GitHub - MyRecall"
