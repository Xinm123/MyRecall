"""SiliconFlow OpenAI-compatible multimodal embedding provider."""
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


class SiliconFlowEmbeddingProvider(MultimodalEmbeddingProvider):
    """SiliconFlow OpenAI-compatible multimodal embedding provider.

    Supports text + image mixed input via SiliconFlow's VL Embedding API.
    Uses the standard OpenAI-compatible /v1/embeddings endpoint.

    API Format:
        POST /v1/embeddings
        {
            "model": "Qwen/Qwen3-VL-Embedding-8B",
            "input": [
                {"text": "..."},
                {"image": "data:image/jpeg;base64,..."}
            ],
            "encoding_format": "float",
            "dimensions": 1024
        }

    Response Format (OpenAI-compatible):
        {
            "object": "list",
            "data": [
                {"object": "embedding", "embedding": [...], "index": 0}
            ],
            "usage": {"prompt_tokens": 123, "total_tokens": 123}
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
            api_base or "https://api.siliconflow.cn/v1"
        )
        self.dimension = dimension
        logger.info(
            f"SiliconFlowEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name} dim={self.dimension}"
        )

    def _request_embedding(self, payload: dict) -> np.ndarray:
        """Send request to SiliconFlow /v1/embeddings and parse response."""
        url = f"{self.api_base}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

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
                raise EmbeddingProviderRequestError("No embedding in response")
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

        # Build SiliconFlow VL request: mixed list of text and image objects
        input_items: list = []
        if text and text.strip():
            input_items.append({"text": text.strip()})
        input_items.append({"image": f"data:image/jpeg;base64,{encoded}"})

        payload = {
            "model": self.model_name,
            "input": input_items,
            "encoding_format": "float",
            "dimensions": self.dimension,
        }

        return self._request_embedding(payload)

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector (self.dimension dimensions)
        """
        if not text or text.isspace():
            return np.zeros(self.dimension, dtype=np.float32)

        payload = {
            "model": self.model_name,
            "input": text,
            "encoding_format": "float",
            "dimensions": self.dimension,
        }

        return self._request_embedding(payload)
