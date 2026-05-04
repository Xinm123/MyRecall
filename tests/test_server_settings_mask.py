"""Unit tests for API key masking function."""

import pytest
from openrecall.server.runtime_config import _mask_api_key


class TestMaskApiKey:
    def test_empty_returns_empty(self):
        assert _mask_api_key("") == ""

    def test_short_returns_stars(self):
        assert _mask_api_key("abc") == "***"

    def test_medium_returns_stars(self):
        assert _mask_api_key("sk-1234") == "***"

    def test_long_returns_first3_last4(self):
        assert _mask_api_key("sk-1234567890XX12") == "sk-***XX12"

    def test_exactly_8_chars(self):
        assert _mask_api_key("12345678") == "123***5678"

    def test_unicode_safe(self):
        assert _mask_api_key("日本語12345678") == "日本語***5678"
