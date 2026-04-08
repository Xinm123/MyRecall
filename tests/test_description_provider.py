"""Tests for description provider models and protocol."""
import json

import pytest

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderError,
    DescriptionProviderConfigError,
    DescriptionProviderRequestError,
    DescriptionProviderUnavailableError,
)


class TestFrameDescription:
    def test_frame_description_to_db_dict(self):
        desc = FrameDescription(
            narrative="User is viewing GitHub sign in page",
            summary="GitHub login page",
            tags=["github", "login", "authentication"],
        )
        db = desc.to_db_dict()
        assert db["narrative"] == "User is viewing GitHub sign in page"
        assert db["summary"] == "GitHub login page"
        assert json.loads(db["tags_json"]) == [
            "github",
            "login",
            "authentication",
        ]

    def test_frame_description_defaults(self):
        desc = FrameDescription(
            narrative="A test",
            summary="Test",
            tags=[],
        )
        assert desc.narrative == "A test"
        assert desc.summary == "Test"
        assert desc.tags == []

    def test_frame_description_tags_lowercase(self):
        desc = FrameDescription(
            narrative="A test",
            summary="Test",
            tags=["GitHub", "LOGIN", "  Auth  ", ""],
        )
        assert desc.tags == ["github", "login", "auth"]


class TestFrameContext:
    def test_frame_context_optional_fields(self):
        ctx = FrameContext()
        assert ctx.app_name is None
        assert ctx.window_name is None
        assert ctx.browser_url is None

    def test_frame_context_with_values(self):
        ctx = FrameContext(
            app_name="Chrome",
            window_name="GitHub",
            browser_url="https://github.com",
        )
        assert ctx.app_name == "Chrome"
        assert ctx.window_name == "GitHub"
        assert ctx.browser_url == "https://github.com"


class TestDescriptionProviderErrors:
    def test_error_hierarchy(self):
        assert issubclass(DescriptionProviderConfigError, DescriptionProviderError)
        assert issubclass(DescriptionProviderRequestError, DescriptionProviderError)
        assert issubclass(DescriptionProviderUnavailableError, DescriptionProviderError)

    def test_can_raise_and_catch_errors(self):
        with pytest.raises(DescriptionProviderError):
            raise DescriptionProviderError("test")
        with pytest.raises(DescriptionProviderConfigError):
            raise DescriptionProviderConfigError("config error")


class TestOpenAIDescriptionProvider:
    def test_init_allows_empty_api_key_for_local_vllm(self):
        """Empty api_key is allowed for local vLLM without auth."""
        from openrecall.server.description.providers.openai import (
            OpenAIDescriptionProvider,
        )

        # Should not raise - empty api_key is allowed for local vLLM
        provider = OpenAIDescriptionProvider(api_key="", model_name="gpt-4o")
        assert provider.api_key == ""
        assert provider.model_name == "gpt-4o"

    def test_init_requires_model_name(self):
        from openrecall.server.description.providers.openai import (
            OpenAIDescriptionProvider,
        )

        with pytest.raises(Exception):  # ConfigError
            OpenAIDescriptionProvider(api_key="sk-test", model_name="")

    def test_prompt_contains_new_fields(self):
        """Verify prompt contains new fields (narrative, summary, tags)."""
        from openrecall.server.description.providers.openai import _PROMPT_TEXT, _EXAMPLE_OUTPUT

        # Verify prompt contains new fields
        assert "tags" in _PROMPT_TEXT
        assert "narrative" in _PROMPT_TEXT
        assert "summary" in _PROMPT_TEXT

        # Verify example output contains new fields
        assert "tags" in _EXAMPLE_OUTPUT
        assert "narrative" in _EXAMPLE_OUTPUT
        assert "summary" in _EXAMPLE_OUTPUT

        # Verify old fields are NOT in prompt
        assert "entities" not in _PROMPT_TEXT
        assert "intent" not in _PROMPT_TEXT


class TestDashScopeDescriptionProvider:
    def test_init_requires_api_key(self):
        from openrecall.server.description.providers.dashscope import (
            DashScopeDescriptionProvider,
        )

        with pytest.raises(Exception):  # ConfigError
            DashScopeDescriptionProvider(api_key="", model_name="qwen-vl-max")

    def test_init_requires_model_name(self):
        from openrecall.server.description.providers.dashscope import (
            DashScopeDescriptionProvider,
        )

        with pytest.raises(Exception):  # ConfigError
            DashScopeDescriptionProvider(api_key="sk-test", model_name="")
