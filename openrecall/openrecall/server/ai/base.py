from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class AIProviderError(Exception):
    pass


class AIProviderConfigError(AIProviderError):
    pass


class AIProviderUnavailableError(AIProviderError):
    pass


class AIProviderRequestError(AIProviderError):
    pass


class AIProvider(ABC):
    @abstractmethod
    def analyze_image(self, image_path: str) -> str:
        raise NotImplementedError


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image_path: str) -> str:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        raise NotImplementedError


class MultimodalEmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def embed_image(self, image_path: str) -> np.ndarray:
        raise NotImplementedError


class RerankerProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        raise NotImplementedError
