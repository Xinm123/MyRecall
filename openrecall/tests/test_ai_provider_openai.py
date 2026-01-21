import base64
from unittest.mock import Mock, patch


def test_openai_provider_builds_chat_completions_request(tmp_path):
    from openrecall.server.ai.providers import OpenAIProvider

    image_bytes = b"fakepngbytes"
    image_path = tmp_path / "test.png"
    image_path.write_bytes(image_bytes)

    response = Mock()
    response.ok = True
    response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("openrecall.server.ai.providers.requests.post", return_value=response) as post:
        provider = OpenAIProvider(
            api_key="test-key",
            model_name="gpt-4o",
            api_base="https://example.com/v1/",
        )
        result = provider.analyze_image(str(image_path))

    assert result == "ok"
    assert post.call_count == 1

    url = post.call_args.args[0]
    assert url == "https://example.com/v1/chat/completions"

    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"

    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "gpt-4o"
    content = payload["messages"][0]["content"]

    encoded = base64.b64encode(image_bytes).decode("ascii")
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == f"data:image/png;base64,{encoded}"
