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
            entities=["GitHub", "Sign in", "Username field"],
            intent="authenticating to GitHub",
            summary="GitHub login page",
        )
        db = desc.to_db_dict()
        assert db["narrative"] == "User is viewing GitHub sign in page"
        assert db["intent"] == "authenticating to GitHub"
        assert db["summary"] == "GitHub login page"
        assert json.loads(db["entities_json"]) == [
            "GitHub",
            "Sign in",
            "Username field",
        ]

    def test_frame_description_defaults(self):
        desc = FrameDescription(
            narrative="A test",
            entities=[],
            intent="testing",
            summary="Test",
        )
        assert desc.narrative == "A test"
        assert desc.entities == []


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
    def test_init_requires_api_key(self):
        from openrecall.server.description.providers.openai import (
            OpenAIDescriptionProvider,
        )

        with pytest.raises(Exception):  # ConfigError
            OpenAIDescriptionProvider(api_key="", model_name="gpt-4o")

    def test_init_requires_model_name(self):
        from openrecall.server.description.providers.openai import (
            OpenAIDescriptionProvider,
        )

        with pytest.raises(Exception):  # ConfigError
            OpenAIDescriptionProvider(api_key="sk-test", model_name="")


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
