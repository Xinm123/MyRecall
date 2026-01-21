from __future__ import annotations

from typing import Dict

from openrecall.server.ai.base import AIProvider, AIProviderConfigError, EmbeddingProvider, OCRProvider
from openrecall.server.ai.providers import (
    DashScopeEmbeddingProvider,
    DashScopeOCRProvider,
    DashScopeProvider,
    LocalEmbeddingProvider,
    LocalOCRProvider,
    LocalProvider,
    OpenAIEmbeddingProvider,
    OpenAIOCRProvider,
    OpenAIProvider,
)
from openrecall.shared.config import settings

_instances: Dict[str, object] = {}


def _resolve_vision_config() -> tuple[str, str, str, str]:
    provider = settings.vision_provider or settings.ai_provider
    model_name = settings.vision_model_name or settings.ai_model_name
    api_key = settings.vision_api_key or settings.ai_api_key
    api_base = settings.vision_api_base or settings.ai_api_base
    return provider, model_name, api_key, api_base


def _resolve_ocr_config() -> tuple[str, str, str, str]:
    provider = settings.ocr_provider or settings.ai_provider
    model_name = settings.ocr_model_name or settings.ai_model_name
    api_key = settings.ocr_api_key or settings.ai_api_key
    api_base = settings.ocr_api_base or settings.ai_api_base
    return provider, model_name, api_key, api_base


def _resolve_embedding_config() -> tuple[str, str, str, str]:
    provider = settings.embedding_provider or settings.ai_provider
    model_name = settings.embedding_api_model_name
    api_key = settings.embedding_api_key or settings.ai_api_key
    api_base = settings.embedding_api_base or settings.ai_api_base
    return provider, model_name, api_key, api_base


def get_ai_provider(capability: str = "vision") -> AIProvider:
    if capability != "vision":
        raise AIProviderConfigError(f"Unsupported capability: {capability}")

    cached = _instances.get(capability)
    if isinstance(cached, AIProvider):
        return cached

    provider, model_name, api_key, api_base = _resolve_vision_config()
    provider = (provider or "local").strip().lower()

    if provider == "local":
        instance: AIProvider = LocalProvider(model_name=model_name)
    elif provider == "dashscope":
        instance = DashScopeProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIProvider(api_key=api_key, model_name=model_name, api_base=api_base)
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
    elif provider == "dashscope":
        instance = DashScopeOCRProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIOCRProvider(api_key=api_key, model_name=model_name, api_base=api_base)
    else:
        raise AIProviderConfigError(f"Unknown OCR provider: {provider}")

    _instances[capability] = instance
    return instance


def get_embedding_provider() -> EmbeddingProvider:
    capability = "embedding"
    cached = _instances.get(capability)
    if isinstance(cached, EmbeddingProvider):
        return cached

    provider, model_name, api_key, api_base = _resolve_embedding_config()
    provider = (provider or "local").strip().lower()

    if provider == "local":
        instance: EmbeddingProvider = LocalEmbeddingProvider()
    elif provider == "dashscope":
        instance = DashScopeEmbeddingProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIEmbeddingProvider(api_key=api_key, model_name=model_name, api_base=api_base)
    else:
        raise AIProviderConfigError(f"Unknown embedding provider: {provider}")

    _instances[capability] = instance
    return instance
