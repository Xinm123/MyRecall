"""Tests for description provider models and protocol."""
import json
from pathlib import Path

import pytest
from openrecall.server.config_server import ServerSettings


@pytest.fixture(autouse=True)
def _init_runtime_config(tmp_path: Path):
    """Initialize runtime_config so providers reading get_description_*() succeed.

    Autouse: every test in this module gets a fresh DB and TOML defaults.
    """
    import openrecall.server.runtime_config as rc
    rc._settings_store = None
    rc._toml_settings = None
    toml = ServerSettings(
        description_provider="openai",
        description_model="gpt-4o",
        description_api_key="",
        description_api_base="",
        description_request_timeout=120,
    )
    rc.init_runtime_config(tmp_path, toml)
    yield
    rc._settings_store = None
    rc._toml_settings = None

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
        from openrecall.server.description.prompts import build_description_prompt

        prompt_text = build_description_prompt()

        # Verify prompt contains new fields
        assert "tags" in prompt_text
        assert "narrative" in prompt_text
        assert "summary" in prompt_text

        # Verify example output contains new fields (embedded in prompt)
        assert "\"narrative\"" in prompt_text
        assert "\"summary\"" in prompt_text
        assert "\"tags\"" in prompt_text

        # Verify old fields are NOT in prompt
        assert "entities" not in prompt_text
        assert '"intent"' not in prompt_text


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


class TestLocalDescriptionProvider:
    @pytest.mark.unit
    def test_local_provider_builds_messages_with_new_prompt(self):
        """Test Local provider builds messages with new prompt format."""
        from openrecall.server.description.prompts import build_description_prompt

        prompt_text = build_description_prompt()

        # Check prompt contains new format keywords
        assert "tags" in prompt_text
        assert "entities" not in prompt_text
        assert '"intent"' not in prompt_text
        assert "100-150 words" in prompt_text
        assert "20-30 words" in prompt_text
