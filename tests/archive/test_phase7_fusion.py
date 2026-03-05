"""Tests for Phase 7 - Embedding Upgrade and Fusion Strategy."""

import importlib
import os
import tempfile
from unittest import mock

import numpy as np
import pytest

pytestmark = pytest.mark.model


class TestNLPEngine:
    """Tests for the upgraded NLPEngine with Qwen3-Embedding."""
    
    @pytest.fixture(scope="class")
    def nlp_engine(self):
        """Load NLP engine once for all tests."""
        from openrecall.server.nlp import NLPEngine
        return NLPEngine()
    
    def test_embedding_dimension(self, nlp_engine):
        """Test that embeddings have correct dimension (1024)."""
        embedding = nlp_engine.encode("Hello Qwen")
        
        assert embedding.shape == (1024,)
        assert embedding.dtype == np.float32
    
    def test_embedding_is_normalized(self, nlp_engine):
        """Test that embeddings are normalized (unit length)."""
        embedding = nlp_engine.encode("Test normalization")
        
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 0.01, f"Expected norm ~1.0, got {norm}"
    
    def test_empty_text_returns_zero_vector(self, nlp_engine):
        """Test that empty text returns zero vector."""
        for empty_input in ["", "   "]:
            embedding = nlp_engine.encode(empty_input)
            assert embedding.shape == (1024,)
            assert np.allclose(embedding, 0)
    
    def test_different_texts_have_different_embeddings(self, nlp_engine):
        """Test that different texts produce different embeddings."""
        emb1 = nlp_engine.encode("User is coding in Python")
        emb2 = nlp_engine.encode("User is watching a movie")
        
        # Cosine similarity should be less than 1.0
        from openrecall.server.nlp import cosine_similarity
        similarity = cosine_similarity(emb1, emb2)
        
        assert similarity < 0.95, f"Embeddings too similar: {similarity}"


class TestFusionStrategy:
    """Tests for the text fusion strategy."""
    
    def test_build_fusion_text_with_both(self):
        """Test fusion with both description and OCR text."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        from openrecall.server.api import _build_fusion_text
        
        result = _build_fusion_text(
            description="User is coding in VS Code",
            ocr_text="def hello():\n    print('world')"
        )
        
        assert "Visual Summary: User is coding in VS Code" in result
        assert "Detailed Content: def hello():" in result
    
    def test_build_fusion_text_description_only(self):
        """Test fusion with only description (OCR failed)."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        from openrecall.server.api import _build_fusion_text
        
        result = _build_fusion_text(
            description="User viewing a video player",
            ocr_text=""
        )
        
        assert result == "Visual Summary: User viewing a video player"
    
    def test_build_fusion_text_ocr_only(self):
        """Test fusion with only OCR text (AI failed)."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        from openrecall.server.api import _build_fusion_text
        
        result = _build_fusion_text(
            description=None,
            ocr_text="Some OCR text"
        )
        
        assert result == "Some OCR text"
    
    def test_build_fusion_text_both_empty(self):
        """Test fusion with both empty (edge case)."""
        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        from openrecall.server.api import _build_fusion_text
        
        result = _build_fusion_text(description=None, ocr_text="")
        assert result == ""


class TestEmbeddingConfig:
    """Tests for embedding configuration."""
    
    def test_embedding_config_defaults(self):
        """Test that embedding config has correct defaults."""
        from openrecall.shared.config import Settings
        
        s = Settings()
        assert "Qwen3-Embedding-0.6B" in s.embedding_model_name
        assert s.embedding_dim == 1024
    
    def test_embedding_model_can_be_overridden(self):
        """Test that embedding model can be set via environment."""
        with mock.patch.dict(os.environ, {
            "OPENRECALL_EMBEDDING_MODEL": "custom/model"
        }):
            from openrecall.shared.config import Settings
            s = Settings()
            assert s.embedding_model_name == "custom/model"


class TestGetEmbeddingFunction:
    """Tests for the convenience get_embedding function."""
    
    def test_get_embedding_returns_correct_shape(self):
        """Test that get_embedding returns correct shape."""
        from openrecall.server.nlp import get_embedding
        
        embedding = get_embedding("Test text")
        assert embedding.shape == (1024,)
        assert embedding.dtype == np.float32
    
    def test_get_embedding_empty_returns_zero(self):
        """Test that get_embedding with empty text returns zeros."""
        from openrecall.server.nlp import get_embedding
        
        embedding = get_embedding("")
        assert np.allclose(embedding, 0)


class TestCosineSimiliarity:
    """Tests for cosine similarity function."""
    
    def test_identical_vectors_have_similarity_one(self):
        """Test that identical vectors have similarity 1.0."""
        from openrecall.server.nlp import cosine_similarity
        
        vec = np.random.rand(1024).astype(np.float32)
        vec = vec / np.linalg.norm(vec)  # Normalize
        
        similarity = cosine_similarity(vec, vec)
        assert abs(similarity - 1.0) < 0.001
    
    def test_orthogonal_vectors_have_similarity_zero(self):
        """Test that orthogonal vectors have similarity 0."""
        from openrecall.server.nlp import cosine_similarity
        
        vec1 = np.zeros(1024, dtype=np.float32)
        vec1[0] = 1.0
        vec2 = np.zeros(1024, dtype=np.float32)
        vec2[1] = 1.0
        
        similarity = cosine_similarity(vec1, vec2)
        assert abs(similarity) < 0.001
    
    def test_zero_vector_returns_zero_similarity(self):
        """Test that zero vector returns 0 similarity."""
        from openrecall.server.nlp import cosine_similarity
        
        vec1 = np.zeros(1024, dtype=np.float32)
        vec2 = np.random.rand(1024).astype(np.float32)
        
        similarity = cosine_similarity(vec1, vec2)
        assert similarity == 0.0
