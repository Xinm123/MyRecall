"""Embedding providers for multimodal vector generation."""
from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)
from openrecall.server.embedding.providers.openai import (
    OpenAIEmbeddingProvider,
    OpenAIMultimodalEmbeddingProvider,  # Backwards compatibility alias
)
from openrecall.server.embedding.providers.dashscope import (
    DashScopeEmbeddingProvider,
)
from openrecall.server.embedding.providers.multimodal import (
    QwenVLEmbeddingProvider,
)

__all__ = [
    # Protocol and errors
    "MultimodalEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigError",
    "EmbeddingProviderRequestError",
    "EmbeddingProviderUnavailableError",
    # Providers
    "OpenAIEmbeddingProvider",
    "OpenAIMultimodalEmbeddingProvider",  # Alias for backwards compat
    "DashScopeEmbeddingProvider",
    "QwenVLEmbeddingProvider",
]
