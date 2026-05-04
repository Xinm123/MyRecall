import pytest
from openrecall.server.ai import factory


class TestFactoryInvalidate:
    def teardown_method(self):
        """Clear factory cache after each test."""
        factory.invalidate()

    def test_invalidate_clears_specific_capability(self):
        factory._instances["description"] = "fake_provider"
        factory.invalidate("description")
        assert "description" not in factory._instances

    def test_invalidate_clears_all_when_none(self):
        factory._instances["description"] = "fake"
        factory._instances["ocr"] = "fake2"
        factory.invalidate()
        assert factory._instances == {}

    def test_invalidate_no_op_when_key_missing(self):
        factory.invalidate("nonexistent")  # should not raise
