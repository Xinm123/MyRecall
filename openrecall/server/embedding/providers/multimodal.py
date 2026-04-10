"""Qwen3-VL embedding provider for qwen3-vl-embedding API."""
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


class QwenVLEmbeddingProvider(MultimodalEmbeddingProvider):
    """Qwen3-VL embedding provider for qwen3-vl-embedding API.

    Supports true fusion of text and image into a single embedding.

    API Format:
        POST /v1/embeddings/multimodal
        {
            "model": "qwen3-vl-embedding",
            "input": {
                "contents": [{"text": "...", "image": "<base64>"}]
            },
            "parameters": {"dimension": 1024}
        }

    Response Format:
        {
            "output": {
                "embeddings": [{"text_index": 0, "image_index": 0, "embedding": [...]}]
            },
            "dimension": 1024
        }
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
        dimension: int = 1024,
    ) -> None:
        if not model_name:
            raise EmbeddingProviderConfigError("model_name is required")

        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(
            api_base or "http://localhost:8070/v1"
        )
        self.dimension = dimension
        logger.info(
            f"QwenVLEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name} dim={self.dimension}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate fused embedding for image with optional text context.

        Args:
            image_path: Path to image file
            text: Optional text context (OCR/AX text)

        Returns:
            Normalized embedding vector (self.dimension dimensions)
        """
        path = Path(image_path).resolve()
        if not path.is_file():
            raise EmbeddingProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/embeddings/multimodal"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Build qwen3-vl-embedding API format
        content = {"image": encoded}
        if text and text.strip():
            content["text"] = text.strip()

        payload = {
            "model": self.model_name,
            "input": {
                "contents": [content]
            },
            "parameters": {
                "dimension": self.dimension
            }
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
            # qwen3-vl-embedding response format
            embeddings = data.get("output", {}).get("embeddings", [])
            if not embeddings:
                raise EmbeddingProviderRequestError(
                    "No embedding in response"
                )
            emb = embeddings[0].get("embedding")
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
            Normalized embedding vector (self.dimension dimensions)
        """
        if not text or text.isspace():
            return np.zeros(self.dimension, dtype=np.float32)

        url = f"{self.api_base}/embeddings/multimodal"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "input": {
                "contents": [{"text": text}]
            },
            "parameters": {
                "dimension": self.dimension
            }
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
            embeddings = data.get("output", {}).get("embeddings", [])
            if not embeddings:
                raise EmbeddingProviderRequestError(
                    "No embedding in response"
                )
            emb = embeddings[0].get("embedding")
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
