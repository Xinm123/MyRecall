"""Tests for embedding providers."""
import pytest
import numpy as np
from unittest.mock import patch, Mock

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


class TestOpenAIMultimodalEmbeddingProvider:
    def test_init_allows_empty_api_key_for_local_vllm(self):
        """Empty api_key is allowed for local vLLM without auth."""
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        provider = OpenAIMultimodalEmbeddingProvider(
            api_key="", model_name="qwen3-vl-embedding"
        )
        assert provider.api_key == ""
        assert provider.model_name == "qwen3-vl-embedding"

    def test_init_requires_model_name(self):
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        with pytest.raises(EmbeddingProviderConfigError):
            OpenAIMultimodalEmbeddingProvider(api_key="sk-test", model_name="")

    def test_init_normalizes_api_base(self):
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        provider = OpenAIMultimodalEmbeddingProvider(
            api_key="test",
            model_name="test-model",
            api_base="http://localhost:8000/v1/",
        )
        assert provider.api_base == "http://localhost:8000/v1"

    def test_embed_text_returns_normalized_vector(self):
        """embed_text should return normalized vector (L2 norm = 1)."""
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        provider = OpenAIMultimodalEmbeddingProvider(
            api_key="test", model_name="test-model"
        )

        # Mock the API response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "data": [{"embedding": [0.5] * 1024}]
        }

        with patch("requests.post", return_value=mock_response):
            result = provider.embed_text("test query")

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        # Check L2 normalization
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001
