"""DashScope native API embedding provider (skeleton)."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderConfigError,
)

logger = logging.getLogger(__name__)


class DashScopeEmbeddingProvider(MultimodalEmbeddingProvider):
    """DashScope native API embedding provider.

    Implementation pending. Will support DashScope's native API format.
    See: https://help.aliyun.com/document_detail/2712537.html

    For now, use 'multimodal' provider with DashScope's OpenAI-compatible mode.
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
        self.api_base = api_base.strip() if api_base else "https://dashscope.aliyuncs.com/api/v1"
        logger.info(
            f"DashScopeEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Not yet implemented. Will use DashScope native multimodal API.
        """
        raise NotImplementedError(
            "DashScope multimodal embedding not yet implemented. "
            "Use 'multimodal' provider with DashScope's OpenAI-compatible mode, "
            "or check https://help.aliyun.com/document_detail/2712537.html"
        )

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Not yet implemented. Will use DashScope native text embedding API.
        """
        raise NotImplementedError(
            "DashScope text embedding not yet implemented. "
            "Use 'multimodal' provider with DashScope's OpenAI-compatible mode, "
            "or check https://help.aliyun.com/document_detail/2712537.html"
        )
