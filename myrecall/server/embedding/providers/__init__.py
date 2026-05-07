"""Embedding providers for multimodal vector generation."""
from myrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)
from myrecall.server.embedding.providers.openai import (
    OpenAIEmbeddingProvider,
    OpenAIMultimodalEmbeddingProvider,  # Backwards compatibility alias
)
from myrecall.server.embedding.providers.dashscope import (
    DashScopeEmbeddingProvider,
)
from myrecall.server.embedding.providers.multimodal import (
    QwenVLEmbeddingProvider,
)
from myrecall.server.embedding.providers.siliconflow import (
    SiliconFlowEmbeddingProvider,
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
    "SiliconFlowEmbeddingProvider",
]
