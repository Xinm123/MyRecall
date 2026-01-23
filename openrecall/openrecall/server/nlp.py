"""NLP engine for semantic embeddings using Qwen3-Embedding."""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class NLPEngine:
    """Embedding engine using Qwen3-Embedding-0.6B.
    
    Provides semantic embeddings for text search and similarity.
    """
    
    def __init__(self) -> None:
        """Initialize the NLP engine with the configured embedding model."""
        logger.info(f"Loading embedding model: {settings.embedding_model_name}")
        logger.info(f"Using device: {settings.device}")
        
        self.model = SentenceTransformer(
            settings.embedding_model_name,
            trust_remote_code=True,
            device=settings.device,
        )
        self.dim = settings.embedding_dim
        
        logger.info(f"Embedding model loaded (dim={self.dim})")
    
    def encode(self, text: str) -> np.ndarray:
        """Generate embedding for the given text.
        
        Args:
            text: Input text to embed.
            
        Returns:
            Normalized embedding vector of shape (embedding_dim,).
        """
        if not text or text.isspace():
            logger.warning("Empty text provided, returning zero vector")
            return np.zeros(self.dim, dtype=np.float32)
        
        try:
            embedding = self.model.encode(
                text,
                normalize_embeddings=True,
            )
            return embedding.astype(np.float32)
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return np.zeros(self.dim, dtype=np.float32)


# Lazy-loaded singleton
_engine: Optional[NLPEngine] = None


def get_nlp_engine() -> NLPEngine:
    """Get or create the singleton NLPEngine instance."""
    global _engine
    if _engine is None:
        _engine = NLPEngine()
    return _engine


def get_embedding(text: str) -> np.ndarray:
    """Convenience function to get embedding for text.
    
    Delegates to the configured EmbeddingProvider via factory.
    
    Args:
        text: Input text to embed.
        
    Returns:
        Embedding vector of shape (embedding_dim,).
    """
    try:
        from openrecall.server.ai.factory import get_embedding_provider
        return get_embedding_provider().embed_text(text)
    except Exception as e:
        logger.error(f"Failed to get embedding: {e}")
        # Return zero vector on failure
        dim = int(getattr(settings, "embedding_dim", 1024))
        return np.zeros(dim, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector.
        b: Second vector.
        
    Returns:
        Cosine similarity score between -1 and 1.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    similarity = np.dot(a, b) / (norm_a * norm_b)
    return float(np.clip(similarity, -1.0, 1.0))
