"""
Unit tests for PHash computation and SimhashCache functionality.

This test module validates:
- PHash computation from PIL Images
- Hamming distance calculation
- Similarity threshold checking
- SimhashCache insertion, eviction, and query operations
"""

from unittest.mock import MagicMock

from PIL import Image

from openrecall.client.hash_utils import (
    SimhashCache,
    compute_phash,
    hamming_distance,
    is_similar,
)


class TestPHashComputation:
    """Tests for PHash computation functionality."""

    def test_compute_phash_returns_int(self):
        """PHash computation should return an integer."""
        img = Image.new("RGB", (100, 100), color="red")
        hash_val = compute_phash(img)
        assert isinstance(hash_val, int)

    def test_compute_phash_identical_images(self):
        """Identical images should produce identical PHash values."""
        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="red")
        hash1 = compute_phash(img1)
        hash2 = compute_phash(img2)
        assert hash1 == hash2

    def test_compute_phash_different_images(self):
        """Visually different images should produce different PHash values."""
        # PHash focuses on structure/texture, not just color
        # Create images with different structures
        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="red")
        # Draw a pattern on img2 to create structural difference
        for i in range(0, 100, 10):
            for j in range(0, 100, 10):
                img2.putpixel((i, j), (0, 0, 0))

        hash1 = compute_phash(img1)
        hash2 = compute_phash(img2)
        # These should have different structure, so different hashes
        assert hash1 != hash2

    def test_compute_phash_robust_to_minor_changes(self):
        """PHash should be robust to minor visual changes."""
        # Create base image
        img1 = Image.new("RGB", (100, 100), color="red")

        # Create slightly different image (simulating compression)
        img2 = Image.new("RGB", (100, 100), color="red")
        # Add a small change
        for x in range(5):
            for y in range(5):
                img2.putpixel((x, y), (255, 0, 1))

        hash1 = compute_phash(img1)
        hash2 = compute_phash(img2)

        # Hamming distance should be small (likely 0-4 bits)
        distance = hamming_distance(hash1, hash2)
        assert distance <= 8  # Within similarity threshold


class TestHammingDistance:
    """Tests for Hamming distance calculation."""

    def test_identical_hashes_distance_zero(self):
        """Identical hashes should have distance 0."""
        assert hamming_distance(0xABC, 0xABC) == 0

    def test_one_bit_difference(self):
        """Hashes differing by one bit should have distance 1."""
        assert hamming_distance(0xABC, 0xABD) == 1

    def test_all_bits_different(self):
        """Completely different hashes should have distance 64."""
        assert hamming_distance(0x0000000000000000, 0xFFFFFFFFFFFFFFFF) == 64

    def test_partial_difference(self):
        """Partially different hashes should have correct distance."""
        # 0xABC = 101010111100
        # 0xABD = 101010111101
        # Differ by 1 bit
        assert hamming_distance(0xABC, 0xABD) == 1


class TestIsSimilar:
    """Tests for similarity checking."""

    def test_identical_hashes_are_similar(self):
        """Identical hashes should be similar."""
        assert is_similar(0xABC, 0xABC, threshold=8) is True

    def test_small_distance_is_similar(self):
        """Small Hamming distance should be similar."""
        # Distance = 1
        assert is_similar(0xABC, 0xABD, threshold=8) is True

    def test_large_distance_is_not_similar(self):
        """Large Hamming distance should not be similar."""
        # Distance = 64 (all bits different)
        assert is_similar(0x000, 0xFFF, threshold=8) is False

    def test_exact_threshold_is_similar(self):
        """Hashes at exact threshold should be similar."""
        # Create two hashes with distance exactly 8
        hash1 = 0x0000000000000000
        hash2 = 0x00000000000000FF  # 8 bits different
        assert hamming_distance(hash1, hash2) == 8
        assert is_similar(hash1, hash2, threshold=8) is True

    def test_one_over_threshold_is_not_similar(self):
        """Hashes one bit over threshold should not be similar."""
        # Create two hashes with distance 9
        hash1 = 0x0000000000000000
        hash2 = 0x00000000000001FF  # 9 bits different
        assert hamming_distance(hash1, hash2) == 9
        assert is_similar(hash1, hash2, threshold=8) is False


class TestSimhashCache:
    """Tests for SimhashCache functionality."""

    def test_add_and_retrieve_timestamp(self):
        """Added entries should update last enqueue time."""
        cache = SimhashCache(cache_size_per_device=5)
        cache.add("monitor_0", 0xABC, timestamp=100.0)

        assert cache.get_last_enqueue_time("monitor_0") == 100.0

    def test_cache_size_enforcement(self, monkeypatch):
        """Cache should evict oldest entries when at capacity."""
        mock_rc = MagicMock()
        mock_rc.get_dedup_cache_size.return_value = 2
        mock_rc.get_dedup_ttl_seconds.return_value = float("inf")
        monkeypatch.setattr("openrecall.client.hash_utils.runtime_config", mock_rc)
        cache = SimhashCache(cache_size_per_device=2)

        cache.add("monitor_0", 0xABC, timestamp=100.0)
        cache.add("monitor_0", 0xDEF, timestamp=200.0)
        cache.add("monitor_0", 0x123, timestamp=300.0)

        # First entry (0xABC) should be evicted
        assert not cache.is_similar_to_cache("monitor_0", 0xABC, threshold=0)
        # Second and third entries should still be present
        assert cache.is_similar_to_cache("monitor_0", 0xDEF, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0x123, threshold=0)

    def test_per_device_isolation(self):
        """Each device should have independent cache."""
        cache = SimhashCache(cache_size_per_device=5)

        cache.add("monitor_0", 0xABC, timestamp=100.0)
        cache.add("monitor_1", 0xDEF, timestamp=200.0)

        # monitor_0 should have 0xABC
        assert cache.is_similar_to_cache("monitor_0", 0xABC, threshold=0)
        assert not cache.is_similar_to_cache("monitor_0", 0xDEF, threshold=0)

        # monitor_1 should have 0xDEF
        assert cache.is_similar_to_cache("monitor_1", 0xDEF, threshold=0)
        assert not cache.is_similar_to_cache("monitor_1", 0xABC, threshold=0)

    def test_similarity_detection(self):
        """Cache should detect similar hashes."""
        cache = SimhashCache(cache_size_per_device=5)
        cache.add("monitor_0", 0xABC, timestamp=100.0)

        # Exact match (distance 0)
        assert cache.is_similar_to_cache("monitor_0", 0xABC, threshold=8)

        # Similar hash (distance 1)
        assert cache.is_similar_to_cache("monitor_0", 0xABD, threshold=8)

        # Not similar - use hashes with large hamming distance
        # 0xABC = 2748, 0xFFF = 4095, distance = 6 (similar with threshold 8)
        # Need hashes with distance > 8
        hash1 = 0x0000000000000000
        hash2 = 0x00000000000001FF  # 9 bits different
        cache.add("monitor_1", hash1, timestamp=200.0)
        assert not cache.is_similar_to_cache("monitor_1", hash2, threshold=8)

    def test_clear_device(self):
        """Clearing a device should remove its cache."""
        cache = SimhashCache(cache_size_per_device=5)
        cache.add("monitor_0", 0xABC, timestamp=100.0)
        cache.add("monitor_1", 0xDEF, timestamp=200.0)

        cache.clear_device("monitor_0")

        # monitor_0 should be cleared
        assert cache.get_last_enqueue_time("monitor_0") is None
        assert not cache.is_similar_to_cache("monitor_0", 0xABC, threshold=0)

        # monitor_1 should still be present
        assert cache.get_last_enqueue_time("monitor_1") == 200.0
        assert cache.is_similar_to_cache("monitor_1", 0xDEF, threshold=0)

    def test_clear_all(self):
        """Clearing all should remove all caches."""
        cache = SimhashCache(cache_size_per_device=5)
        cache.add("monitor_0", 0xABC, timestamp=100.0)
        cache.add("monitor_1", 0xDEF, timestamp=200.0)

        cache.clear()

        assert cache.get_last_enqueue_time("monitor_0") is None
        assert cache.get_last_enqueue_time("monitor_1") is None

    def test_empty_cache_returns_none(self):
        """Empty cache should return None for last enqueue time."""
        cache = SimhashCache(cache_size_per_device=5)
        assert cache.get_last_enqueue_time("monitor_0") is None

    def test_non_existent_device_not_similar(self):
        """Non-existent device should not report similarity."""
        cache = SimhashCache(cache_size_per_device=5)
        assert not cache.is_similar_to_cache("monitor_0", 0xABC, threshold=8)

    def test_multiple_similar_hashes_in_cache(self, monkeypatch):
        """Cache should detect similarity if any cached hash is similar."""
        mock_rc = MagicMock()
        mock_rc.get_dedup_cache_size.return_value = 3
        mock_rc.get_dedup_ttl_seconds.return_value = float("inf")
        monkeypatch.setattr("openrecall.client.hash_utils.runtime_config", mock_rc)
        cache = SimhashCache(cache_size_per_device=3)
        cache.add("monitor_0", 0xABC, timestamp=100.0)
        cache.add("monitor_0", 0xDEF, timestamp=200.0)
        cache.add("monitor_0", 0x123, timestamp=300.0)

        # Should match any of the cached hashes
        assert cache.is_similar_to_cache("monitor_0", 0xABC, threshold=0)  # Exact match
        assert cache.is_similar_to_cache("monitor_0", 0xDEF, threshold=0)  # Exact match
        assert cache.is_similar_to_cache("monitor_0", 0x123, threshold=0)  # Exact match

        # Similar to 0xABC (distance 1)
        assert cache.is_similar_to_cache("monitor_0", 0xABD, threshold=8)

    def test_fifo_eviction_order(self, monkeypatch):
        """Cache should evict entries in FIFO order."""
        mock_rc = MagicMock()
        mock_rc.get_dedup_cache_size.return_value = 2
        mock_rc.get_dedup_ttl_seconds.return_value = float("inf")
        monkeypatch.setattr("openrecall.client.hash_utils.runtime_config", mock_rc)
        cache = SimhashCache(cache_size_per_device=2)

        cache.add("monitor_0", 0xABC, timestamp=100.0)  # Oldest
        cache.add("monitor_0", 0xDEF, timestamp=200.0)  # Middle
        cache.add("monitor_0", 0x123, timestamp=300.0)  # Newest

        # First entry should be evicted
        assert not cache.is_similar_to_cache("monitor_0", 0xABC, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0xDEF, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0x123, threshold=0)

        cache.add("monitor_0", 0x456, timestamp=400.0)

        # Second entry should now be evicted
        assert not cache.is_similar_to_cache("monitor_0", 0xDEF, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0x123, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0x456, threshold=0)
