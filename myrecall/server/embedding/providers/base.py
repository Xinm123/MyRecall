"""Embedding provider protocol and errors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class EmbeddingProviderError(Exception):
    """Base error for embedding providers."""
    pass


class EmbeddingProviderConfigError(EmbeddingProviderError):
    """Configuration error."""
    pass


class EmbeddingProviderRequestError(EmbeddingProviderError):
    """Request/execution error."""
    pass


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Provider unavailable (missing dependency, etc)."""
    pass


class MultimodalEmbeddingProvider(ABC):
    """Protocol for multimodal embedding providers.

    Supports both image+text fusion embedding and text-only embedding.
    """

    @abstractmethod
    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Args:
            image_path: Path to image file (JPEG/PNG)
            text: Optional text context (OCR/AX text from frame.full_text)

        Returns:
            Normalized embedding vector (1024 dimensions)

        Raises:
            EmbeddingProviderRequestError: On API/SDK error
            EmbeddingProviderUnavailableError: On missing dependencies
        """
        raise NotImplementedError

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text for semantic search

        Returns:
            Normalized embedding vector (1024 dimensions)

        Raises:
            EmbeddingProviderRequestError: On API/SDK error
        """
        raise NotImplementedError
