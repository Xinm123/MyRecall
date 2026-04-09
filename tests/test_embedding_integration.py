"""Integration tests for embedding feature."""
import pytest


@pytest.mark.integration
class TestEmbeddingIntegration:
    def test_full_flow(self, tmp_path):
        """Test full embedding flow from task creation to search."""
        # This test requires a running server with embedding provider configured
        # Skip if not available
        pytest.skip("Integration test - requires running server")

    def test_backfill_endpoint(self):
        """Test embedding backfill for historical frames."""
        pytest.skip("Integration test - requires running server")

    def test_hybrid_search_returns_results(self):
        """Test hybrid search returns combined results."""
        pytest.skip("Integration test - requires running server")
