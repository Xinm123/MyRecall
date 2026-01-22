from __future__ import annotations

import logging
from typing import Dict

import numpy as np

from openrecall.server.ai.base import (
    AIProvider,
    AIProviderConfigError,
    AIProviderError,
    EmbeddingProvider,
    MultimodalEmbeddingProvider,
    OCRProvider,
    RerankerProvider,
)
from openrecall.server.ai.providers import (
    DashScopeEmbeddingProvider,
    DashScopeOCRProvider,
    DashScopeProvider,
    LocalEmbeddingProvider,
    LocalOCRProvider,
    LocalProvider,
    LocalMMEmbeddingProvider,
    LocalRerankerProvider,
    OpenAIMMEmbeddingProvider,
    OpenAIEmbeddingProvider,
    OpenAIOCRProvider,
    OpenAIRerankerProvider,
    OpenAIProvider,
    PaddleOCRProvider,
)
from openrecall.shared.config import settings

_instances: Dict[str, object] = {}
logger = logging.getLogger("openrecall.server.ai.factory")


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


def _resolve_mm_embedding_config() -> tuple[str, str, str, str]:
    provider = (settings.mm_embedding_provider or "api").strip()
    model_name = settings.mm_embedding_model_name.strip()
    api_key = settings.mm_embedding_api_key.strip()
    api_base = settings.mm_embedding_api_base.strip()
    return provider, model_name, api_key, api_base


def _resolve_rerank_config() -> tuple[str, str, str, str]:
    provider = (settings.rerank_provider or "api").strip()
    model_name = settings.rerank_model_name.strip()
    api_key = (settings.ai_api_key or "").strip()
    api_base = (settings.ai_api_base or "").strip()
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

    logger.info(f"vision provider={provider} model={model_name or '(default)'}")
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
    elif provider == "paddleocr":
        instance = PaddleOCRProvider()
    elif provider == "dashscope":
        instance = DashScopeOCRProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIOCRProvider(api_key=api_key, model_name=model_name, api_base=api_base)
    else:
        raise AIProviderConfigError(f"Unknown OCR provider: {provider}")

    logger.info(f"ocr provider={provider} model={model_name or '(default/local)'}")
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

    logger.info(f"embedding provider={provider} model={model_name or '(default)'}")
    _instances[capability] = instance
    return instance


class _FallbackMMEmbeddingProvider(MultimodalEmbeddingProvider):
    def __init__(self, dim: int) -> None:
        self._dim = int(dim)

    def embed_text(self, text: str) -> np.ndarray:
        return np.zeros(self._dim, dtype=np.float32)

    def embed_image(self, image_path: str) -> np.ndarray:
        return np.zeros(self._dim, dtype=np.float32)


class _FallbackRerankerProvider(RerankerProvider):
    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        return candidates


def get_mm_embedding_provider() -> MultimodalEmbeddingProvider:
    capability = "mm_embedding"
    cached = _instances.get(capability)
    if isinstance(cached, MultimodalEmbeddingProvider):
        return cached

    provider, _model_name, _api_key, _api_base = _resolve_mm_embedding_config()
    provider = (provider or "api").strip().lower()

    try:
        if provider in {"api", "openai"}:
            instance = OpenAIMMEmbeddingProvider(
                api_key=_api_key,
                model_name=_model_name,
                api_base=_api_base,
            )
        elif provider == "local":
            instance = LocalMMEmbeddingProvider(model_name=_model_name)
        else:
            raise AIProviderConfigError(f"Unknown multimodal embedding provider: {provider}")
    except AIProviderError as e:
        logger.warning(
            f"mm_embedding fallback enabled (provider={provider} model={_model_name or '(missing)'}): {e}"
        )
        instance = _FallbackMMEmbeddingProvider(dim=settings.embedding_dim)

    logger.info(f"mm_embedding provider={provider} model={_model_name or '(default)'}")
    _instances[capability] = instance
    return instance


def get_reranker_provider() -> RerankerProvider:
    capability = "rerank"
    cached = _instances.get(capability)
    if isinstance(cached, RerankerProvider):
        return cached

    provider, _model_name, _api_key, _api_base = _resolve_rerank_config()
    provider = (provider or "api").strip().lower()

    try:
        if provider in {"api", "openai"}:
            instance = OpenAIRerankerProvider(
                api_key=_api_key,
                model_name=_model_name,
                api_base=_api_base,
            )
        elif provider == "local":
            instance = LocalRerankerProvider(model_name=_model_name)
        else:
            raise AIProviderConfigError(f"Unknown reranker provider: {provider}")
    except AIProviderError as e:
        logger.warning(f"rerank fallback enabled (provider={provider} model={_model_name or '(missing)'}): {e}")
        instance = _FallbackRerankerProvider()

    logger.info(f"rerank provider={provider} model={_model_name or '(default)'}")
    _instances[capability] = instance
    return instance
