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


class TestQwenVLEmbeddingProvider:
    def test_init_allows_empty_api_key(self):
        """Empty api_key is allowed for local services without auth."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        provider = QwenVLEmbeddingProvider(
            api_key="", model_name="qwen3-vl-embedding", dimension=1024
        )
        assert provider.api_key == ""
        assert provider.model_name == "qwen3-vl-embedding"
        assert provider.dimension == 1024

    def test_init_requires_model_name(self):
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        with pytest.raises(EmbeddingProviderConfigError):
            QwenVLEmbeddingProvider(api_key="test", model_name="", dimension=1024)

    def test_init_normalizes_api_base(self):
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        provider = QwenVLEmbeddingProvider(
            api_key="test",
            model_name="test-model",
            api_base="http://localhost:8070/v1/",
            dimension=1024,
        )
        assert provider.api_base == "http://localhost:8070/v1"

    def test_embed_text_returns_normalized_vector(self):
        """embed_text should return normalized vector (L2 norm = 1)."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        provider = QwenVLEmbeddingProvider(
            api_key="test", model_name="test-model", dimension=1024
        )

        # Mock the API response - qwen3-vl-embedding format
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "output": {
                "embeddings": [{"text_index": 0, "image_index": -1, "embedding": [0.5] * 1024}]
            },
            "dimension": 1024
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = provider.embed_text("test query")

            # Verify qwen3-vl-embedding request format
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["model"] == "test-model"
            assert payload["input"]["contents"] == [{"text": "test query"}]
            assert payload["parameters"]["dimension"] == 1024

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001

    def test_embed_image_returns_normalized_vector(self, tmp_path):
        """embed_image should return normalized vector for fused image+text."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        provider = QwenVLEmbeddingProvider(
            api_key="test", model_name="test-model", dimension=1024
        )

        # Mock the API response - qwen3-vl-embedding format with fusion
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "output": {
                "embeddings": [
                    {"text_index": 0, "image_index": 0, "embedding": [0.5] * 1024}
                ]
            },
            "dimension": 1024
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = provider.embed_image(str(test_image), text="test context")

            # Verify qwen3-vl-embedding request format
            call_args = mock_post.call_args
            url = call_args[1]["url"] if "url" in call_args[1] else call_args[0][0]
            assert "/embeddings/multimodal" in url

            payload = call_args[1]["json"]
            content = payload["input"]["contents"][0]
            assert "image" in content
            assert content["text"] == "test context"
            assert payload["parameters"]["dimension"] == 1024

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001

    def test_embed_image_without_text_omits_text_field(self, tmp_path):
        """embed_image without text should only include image in content."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        provider = QwenVLEmbeddingProvider(
            api_key="test", model_name="test-model", dimension=1024
        )

        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "output": {
                "embeddings": [{"text_index": -1, "image_index": 0, "embedding": [0.5] * 1024}]
            }
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            provider.embed_image(str(test_image), text=None)

            payload = mock_post.call_args[1]["json"]
            content = payload["input"]["contents"][0]
            assert "image" in content
            assert "text" not in content


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

    def test_embed_image_returns_normalized_vector(self, tmp_path):
        """embed_image should return normalized vector for image input."""
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        # Create a test image file
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

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
            result = provider.embed_image(str(test_image), text="test context")

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        # Check L2 normalization
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001
