from unittest.mock import Mock, patch

import numpy as np


def test_openai_mm_embedding_provider_builds_text_and_image_requests(tmp_path):
    from openrecall.server.ai.providers import OpenAIMMEmbeddingProvider
    from openrecall.shared.config import settings

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fakepngbytes")

    response = Mock()
    response.ok = True
    response.json.return_value = {"data": [{"embedding": [1.0, 0.0, 0.0]}]}

    with patch("openrecall.server.ai.providers.requests.post", return_value=response) as post:
        provider = OpenAIMMEmbeddingProvider(
            api_key="test-key",
            model_name="qwen3-vl-embedding",
            api_base="https://example.com/v1/",
        )
        vec_t = provider.embed_text("hello")
        vec_i = provider.embed_image(str(image_path))

    assert isinstance(vec_t, np.ndarray)
    assert isinstance(vec_i, np.ndarray)
    assert vec_t.dtype == np.float32
    assert vec_i.dtype == np.float32
    assert vec_t.shape == (settings.embedding_dim,)
    assert vec_i.shape == (settings.embedding_dim,)
    assert abs(float(np.linalg.norm(vec_t)) - 1.0) < 1e-3
    assert abs(float(np.linalg.norm(vec_i)) - 1.0) < 1e-3

    calls = post.call_args_list
    assert len(calls) == 2

    url1 = calls[0].args[0]
    payload1 = calls[0].kwargs["json"]
    assert url1 == "https://example.com/v1/embeddings"
    assert payload1["model"] == "qwen3-vl-embedding"
    assert payload1["input"] == "hello"
    assert payload1["encoding_format"] == "float"

    url2 = calls[1].args[0]
    payload2 = calls[1].kwargs["json"]
    assert url2 == "https://example.com/v1/embeddings"
    assert payload2["model"] == "qwen3-vl-embedding"
    assert isinstance(payload2["input"], list)
    assert payload2["input"][0]["type"] == "image_url"
    assert payload2["encoding_format"] == "float"
