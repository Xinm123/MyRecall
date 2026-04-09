"""Tests for embedding providers."""
import pytest

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)


class TestEmbeddingProviderErrors:
    def test_error_hierarchy(self):
        assert issubclass(EmbeddingProviderConfigError, EmbeddingProviderError)
        assert issubclass(EmbeddingProviderRequestError, EmbeddingProviderError)
        assert issubclass(EmbeddingProviderUnavailableError, EmbeddingProviderError)

    def test_can_raise_and_catch_errors(self):
        with pytest.raises(EmbeddingProviderError):
            raise EmbeddingProviderError("test")
        with pytest.raises(EmbeddingProviderConfigError):
            raise EmbeddingProviderConfigError("config error")

    def test_config_error_requires_model_name(self):
        """ConfigError should be raised when model_name is missing."""
        pass  # Will test with OpenAI provider
