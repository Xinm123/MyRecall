from unittest.mock import Mock, patch


def test_openai_reranker_provider_reorders_by_score():
    from openrecall.server.ai.providers import OpenAIRerankerProvider

    response = Mock()
    response.ok = True
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "{\"scores\":[{\"id\":1,\"score\":0.1},{\"id\":2,\"score\":0.9}]}"
                }
            }
        ]
    }

    with patch("openrecall.server.ai.providers.requests.post", return_value=response):
        provider = OpenAIRerankerProvider(
            api_key="test-key",
            model_name="qwen3-vl-reranker",
            api_base="https://example.com/v1/",
        )
        reranked = provider.rerank(
            "query",
            [
                {"id": 1, "text": "a"},
                {"id": 2, "text": "b"},
            ],
        )

    assert [c["id"] for c in reranked] == [2, 1]
