"""OpenAI text embedding provider."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import requests

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
)
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _normalize_api_base(api_base: str) -> str:
    """Remove trailing slash from API base URL."""
    base = api_base.strip().strip("`\"' ")
    return base[:-1] if base.endswith("/") else base


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2 normalize a vector."""
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec.astype(np.float32, copy=False)
    return (vec / norm).astype(np.float32)


# Backwards compatibility alias (defined after class)
OpenAIMultimodalEmbeddingProvider: type


class OpenAIEmbeddingProvider(MultimodalEmbeddingProvider):
    """OpenAI text embedding provider.

    Supports OpenAI official /v1/embeddings API (text only).
    For multimodal embedding, use 'multimodal' or 'dashscope' provider.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not model_name:
            raise EmbeddingProviderConfigError("model_name is required")

        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(
            api_base or "https://api.openai.com/v1"
        )
        logger.info(
            f"OpenAIEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """OpenAI does not support image embedding.

        Raises:
            EmbeddingProviderRequestError: Always, with guidance to use
                'multimodal' or 'dashscope' provider.
        """
        raise EmbeddingProviderRequestError(
            "OpenAI does not support image embedding. "
            "Use 'multimodal' or 'dashscope' provider."
        )

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector
        """
        if not text or text.isspace():
            return np.zeros(1024, dtype=np.float32)

        url = f"{self.api_base}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "input": text,
            "encoding_format": "float",
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.ai_request_timeout,
            )
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: {e}"
            ) from e

        if not resp.ok:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: status={resp.status_code} "
                f"body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            items = data.get("data") or []
            if not items:
                raise EmbeddingProviderRequestError(
                    "No embedding in response"
                )
            emb = items[0].get("embedding")
            if not isinstance(emb, list):
                raise EmbeddingProviderRequestError(
                    "Invalid embedding format in response"
                )
            vec = np.array(emb, dtype=np.float32)
            return _l2_normalize(vec)
        except EmbeddingProviderRequestError:
            raise
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Failed to parse embedding response: {e}"
            ) from e


# Backwards compatibility alias
OpenAIMultimodalEmbeddingProvider = OpenAIEmbeddingProvider
