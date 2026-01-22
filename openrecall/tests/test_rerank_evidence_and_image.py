import json
from unittest.mock import Mock, patch


def _mk_ok_response(content: str):
    resp = Mock()
    resp.ok = True
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def test_reranker_payload_includes_evidence_fields():
    from openrecall.server.ai.providers import OpenAIRerankerProvider

    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        user_msg = (json or {}).get("messages", [])[1]
        payload = user_msg.get("content")
        parsed = jsonlib.loads(payload)
        seen["candidates"] = parsed["candidates"]
        return _mk_ok_response('{"scores":[{"id":1,"score":0.2}]}')

    import json as jsonlib

    with patch("openrecall.server.ai.providers.requests.post", side_effect=fake_post):
        provider = OpenAIRerankerProvider(
            api_key="k",
            model_name="m",
            api_base="https://example.com/v1/",
        )
        provider.rerank(
            "query",
            [
                {
                    "id": 1,
                    "timestamp": 1710000000,
                    "time_bucket": "下午",
                    "scene": "在浏览器阅读文档",
                    "actions": ["阅读"],
                    "entities": ["openrecall"],
                    "keywords": ["docs", "search"],
                    "ui_text": ["Search", "Settings"],
                    "text": "Search Settings",
                    "description_text": "在浏览器阅读文档",
                }
            ],
        )

    assert "candidates" in seen
    c = seen["candidates"][0]
    assert c["scene"] == "在浏览器阅读文档"
    assert c["time_bucket"] == "下午"
    assert c["actions"] == ["阅读"]


def test_reranker_multimodal_per_candidate_when_image_present():
    from openrecall.server.ai.providers import OpenAIRerankerProvider

    responses = [_mk_ok_response('{"score":0.1}'), _mk_ok_response('{"score":0.9}')]

    with patch("openrecall.server.ai.providers.requests.post", side_effect=responses) as p:
        provider = OpenAIRerankerProvider(
            api_key="k",
            model_name="m",
            api_base="https://example.com/v1/",
        )
        out = provider.rerank(
            "query",
            [
                {"id": 1, "text": "a", "image_url": "data:image/png;base64,AAAA"},
                {"id": 2, "text": "b", "image_url": "data:image/png;base64,BBBB"},
            ],
        )

    assert p.call_count == 2
    assert [c["id"] for c in out] == [2, 1]
