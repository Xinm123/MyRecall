from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Union

if TYPE_CHECKING:
    from openrecall.server.description.providers.base import DescriptionProvider
    from openrecall.server.embedding.providers.base import MultimodalEmbeddingProvider

from openrecall.server.ai.base import (
    AIProvider,
    AIProviderConfigError,
    EmbeddingProvider,
    OCRProvider,
)
from openrecall.server.ai.providers import (
    DashScopeEmbeddingProvider,
    DashScopeOCRProvider,
    DoctrOCRProvider,
    LocalEmbeddingProvider,
    LocalOCRProvider,
    OpenAIEmbeddingProvider,
    OpenAIOCRProvider,
    RapidOCRProvider,
)
from openrecall.shared.config import settings

_instances: Dict[str, object] = {}


def _resolve_ocr_config() -> tuple[str, str, str, str]:
    provider = settings.ocr_provider or settings.ai_provider
    model_name = settings.ocr_model_name or settings.ai_model_name
    api_key = settings.ocr_api_key or settings.ai_api_key
    api_base = settings.ocr_api_base or settings.ai_api_base
    return provider, model_name, api_key, api_base


def get_ai_provider(
    capability: str = "vision",
) -> Union[AIProvider, OCRProvider, EmbeddingProvider]:
    if capability == "embedding":
        return get_embedding_provider()
    elif capability == "ocr":
        return get_ocr_provider()
    elif capability != "vision":
        raise AIProviderConfigError(f"Unsupported capability: {capability}")

    cached = _instances.get(capability)
    if isinstance(cached, AIProvider):
        return cached

    # Vision provider uses global [ai] settings (no separate [vision] section)
    provider = settings.ai_provider
    model_name = settings.ai_model_name
    api_key = settings.ai_api_key
    api_base = settings.ai_api_base
    provider = (provider or "local").strip().lower()

    # Import here to avoid circular dependency at module level
    from openrecall.server.ai.providers import (
        DashScopeProvider,
        LocalProvider,
        OpenAIProvider,
    )

    if provider == "local":
        instance: AIProvider = LocalProvider(model_name=model_name)
    elif provider == "dashscope":
        instance = DashScopeProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIProvider(
            api_key=api_key, model_name=model_name, api_base=api_base
        )
    else:
        raise AIProviderConfigError(f"Unknown AI provider: {provider}")

    _instances[capability] = instance
    return instance


def get_ocr_provider() -> OCRProvider:
    capability = "ocr"
    cached = _instances.get(capability)
    if isinstance(cached, OCRProvider):
        return cached

    provider, model_name, api_key, api_base = _resolve_ocr_config()
    provider = (provider or "local").strip().lower()

    if provider == "local":
        instance: OCRProvider = LocalOCRProvider()
    elif provider == "rapidocr":
        instance = RapidOCRProvider()
    elif provider == "doctr":
        instance = DoctrOCRProvider()
    elif provider == "dashscope":
        instance = DashScopeOCRProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIOCRProvider(
            api_key=api_key, model_name=model_name, api_base=api_base
        )
    else:
        raise AIProviderConfigError(f"Unknown OCR provider: {provider}")

    _instances[capability] = instance
    return instance


def get_embedding_provider() -> EmbeddingProvider:
    capability = "embedding"
    cached = _instances.get(capability)
    if isinstance(cached, EmbeddingProvider):
        return cached

    # Embedding provider uses global [ai] settings (no separate [embedding] section)
    provider = settings.ai_provider
    model_name = settings.ai_model_name
    api_key = settings.ai_api_key
    api_base = settings.ai_api_base
    provider = (provider or "local").strip().lower()

    if provider == "local":
        instance: EmbeddingProvider = LocalEmbeddingProvider()
    elif provider == "dashscope":
        instance = DashScopeEmbeddingProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIEmbeddingProvider(
            api_key=api_key, model_name=model_name, api_base=api_base
        )
    else:
        raise AIProviderConfigError(f"Unknown embedding provider: {provider}")

    _instances[capability] = instance
    return instance


def get_description_provider() -> "DescriptionProvider":
    """Get or create a cached DescriptionProvider instance.

    Description provider uses independent [description] section configuration.
    No fallback to [ai] section - description must be explicitly configured.
    """
    capability = "description"
    cached = _instances.get(capability)
    if cached is not None:
        return cached  # type: ignore[return-value]

    # Lazy import to avoid circular dependency
    from openrecall.server.description.providers import (
        LocalDescriptionProvider,
        OpenAIDescriptionProvider,
        DashScopeDescriptionProvider,
    )

    # Use [description] section only - no fallback to [ai]
    provider = settings.description_provider.strip().lower() if settings.description_provider else "local"
    model_name = settings.description_model
    api_key = settings.description_api_key
    api_base = settings.description_api_base

    if provider == "local":
        instance: DescriptionProvider = LocalDescriptionProvider(model_name=model_name)
    elif provider == "dashscope":
        instance = DashScopeDescriptionProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIDescriptionProvider(
            api_key=api_key, model_name=model_name, api_base=api_base
        )
    else:
        raise AIProviderConfigError(f"Unknown description provider: {provider}")

    _instances[capability] = instance
    return instance


def get_multimodal_embedding_provider() -> "MultimodalEmbeddingProvider":
    """Get or create a cached MultimodalEmbeddingProvider instance.

    Supports providers: openai, dashscope, multimodal, siliconflow
    """
    from openrecall.server.embedding.providers import (
        MultimodalEmbeddingProvider,
        OpenAIEmbeddingProvider,
        DashScopeEmbeddingProvider,
        QwenVLEmbeddingProvider,
        SiliconFlowEmbeddingProvider,
    )

    capability = "multimodal_embedding"
    cached = _instances.get(capability)
    if cached is not None:
        return cached  # type: ignore[return-value]

    provider = settings.embedding_provider.strip().lower() if settings.embedding_provider else "openai"
    model_name = settings.embedding_model
    api_key = settings.embedding_api_key
    api_base = settings.embedding_api_base
    dimension = settings.embedding_dim

    if provider == "openai":
        instance: MultimodalEmbeddingProvider = OpenAIEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    elif provider == "dashscope":
        instance = DashScopeEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    elif provider == "multimodal":
        instance = QwenVLEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
            dimension=dimension,
        )
    elif provider == "siliconflow":
        instance = SiliconFlowEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
            dimension=dimension,
        )
    else:
        raise AIProviderConfigError(f"Unknown embedding provider: {provider}")

    _instances[capability] = instance
    return instance
