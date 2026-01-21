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
