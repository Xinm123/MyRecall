"""Frame embedding module for multimodal vector search."""
from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.embedding.service import EmbeddingService
from openrecall.server.embedding.providers import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)

__all__ = [
    "FrameEmbedding",
    "EmbeddingService",
    "MultimodalEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigError",
    "EmbeddingProviderRequestError",
    "EmbeddingProviderUnavailableError",
]
