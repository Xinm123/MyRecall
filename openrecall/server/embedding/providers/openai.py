"""OpenAI-compatible multimodal embedding provider."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
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


class OpenAIMultimodalEmbeddingProvider(MultimodalEmbeddingProvider):
    """OpenAI-compatible multimodal embedding provider.

    Supports cloud APIs (OpenAI, DashScope) and local network services (vLLM).
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
            f"OpenAIMultimodalEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Args:
            image_path: Path to image file
            text: Optional text context (OCR/AX text)

        Returns:
            Normalized embedding vector
        """
        path = Path(image_path).resolve()
        if not path.is_file():
            raise EmbeddingProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Build multimodal input
        # NOTE: API format varies by provider. This implementation supports:
        # 1. OpenAI-style text-only: {"input": "text", ...}
        # 2. Multimodal with image+text (provider-specific):
        #    - Some providers use: {"input": {"image": "...", "text": "..."}}
        #    - Others use: {"input": [...], "modalities": ["image", "text"]}
        #
        # For qwen3-vl-embedding via vLLM/DashScope, verify the exact format.
        # Current implementation uses a generic format that may need adjustment.
        input_data = {
            "image": f"data:image/jpeg;base64,{encoded}",
        }
        if text:
            input_data["text"] = text

        payload = {
            "model": self.model_name,
            "input": input_data,
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

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector
        """
        if not text or text.isspace():
            # Return zero vector for empty text
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
