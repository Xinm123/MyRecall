import numpy as np
from unittest.mock import Mock, patch


def test_openai_embedding_provider_builds_embeddings_request():
    from openrecall.server.ai.providers import OpenAIEmbeddingProvider

    response = Mock()
    response.ok = True
    response.json.return_value = {"data": [{"embedding": [1.0, 0.0, 0.0]}]}

    with patch("openrecall.server.ai.providers.requests.post", return_value=response) as post:
        provider = OpenAIEmbeddingProvider(
            api_key="test-key",
            model_name="text-embedding-3-large",
            api_base="https://example.com/v1/",
        )
        vec = provider.embed_text("hello")

    assert isinstance(vec, np.ndarray)
    assert vec.dtype == np.float32
    assert vec.shape[0] > 0

    url = post.call_args.args[0]
    assert url == "https://example.com/v1/embeddings"

    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "text-embedding-3-large"
    assert payload["input"] == "hello"
    assert payload["encoding_format"] == "float"


def test_openai_ocr_provider_builds_chat_completions_request(tmp_path):
    from openrecall.server.ai.providers import OpenAIOCRProvider

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fakepngbytes")

    response = Mock()
    response.ok = True
    response.json.return_value = {"choices": [{"message": {"content": "OCR"}}]}

    with patch("openrecall.server.ai.providers.requests.post", return_value=response) as post:
        provider = OpenAIOCRProvider(
            api_key="test-key",
            model_name="gpt-4o",
            api_base="https://example.com/v1/",
        )
        text = provider.extract_text(str(image_path))

    assert text == "OCR"
    url = post.call_args.args[0]
    assert url == "https://example.com/v1/chat/completions"
