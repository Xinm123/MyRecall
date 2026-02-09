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


from typing import Any

class AIProvider(ABC):
    @abstractmethod
    def analyze_image(self, image_path: str) -> dict[str, Any]:
        """
        Analyze the image and return a JSON dictionary.
        Expected keys: 'caption', 'scene', 'action'.
        """
        raise NotImplementedError


class OCRProvider(ABC):
    engine_name: str = "unknown"

    @abstractmethod
    def extract_text(self, image_path: str) -> str:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        raise NotImplementedError
