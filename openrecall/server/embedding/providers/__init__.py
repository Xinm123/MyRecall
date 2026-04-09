"""Embedding providers for multimodal vector generation."""
from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)
from openrecall.server.embedding.providers.openai import (
    OpenAIMultimodalEmbeddingProvider,
)

__all__ = [
    "MultimodalEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigError",
    "EmbeddingProviderRequestError",
    "EmbeddingProviderUnavailableError",
    "OpenAIMultimodalEmbeddingProvider",
]
