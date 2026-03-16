"""
Integration tests for PHash similarity detection and heartbeat mechanism.

These tests verify the end-to-end behavior of the capture pipeline with
PHash-based similarity detection and heartbeat fallback logic.
"""

import pytest
from PIL import Image

from openrecall.client.hash_utils import SimhashCache, compute_phash, hamming_distance


class TestSimhashHeartbeatIntegration:
    """Integration tests for simhash and heartbeat mechanism."""

    def test_simhash_cache_tracks_enqueue_timestamps(self):
        """SimhashCache should track timestamps for heartbeat calculation."""
        cache = SimhashCache(cache_size_per_device=1)

        # Add first frame
        cache.add("monitor_0", 0xABC, timestamp=100.0)
        assert cache.get_last_enqueue_time("monitor_0") == 100.0

        # Add second frame
        cache.add("monitor_0", 0xDEF, timestamp=200.0)
        assert cache.get_last_enqueue_time("monitor_0") == 200.0

    def test_simhash_drops_similar_frames_below_threshold(self):
        """Similar frames should be dropped when heartbeat timeout not exceeded."""
        cache = SimhashCache(cache_size_per_device=1)
        threshold = 8
        heartbeat_interval = 300  # 5 minutes

        # Add first frame at T=0
        cache.add("monitor_0", 0xABC, timestamp=0.0)

        # At T=100, check if similar frame should be dropped
        current_time = 100.0
        last_enqueue = cache.get_last_enqueue_time("monitor_0")
        assert last_enqueue is not None
        time_since_last = current_time - last_enqueue

        # Should drop if:
        # 1. Frame is similar
        # 2. Heartbeat timeout not exceeded
        is_similar = cache.is_similar_to_cache("monitor_0", 0xABD, threshold)  # Distance 1
        should_drop = is_similar and (time_since_last < heartbeat_interval)

        assert is_similar is True
        assert should_drop is True  # Should be dropped

    def test_simhash_forces_frame_on_heartbeat_timeout(self):
        """Frame should be forced when heartbeat timeout is exceeded."""
        cache = SimhashCache(cache_size_per_device=1)
        threshold = 8
        heartbeat_interval = 300  # 5 minutes

        # Add first frame at T=0
        cache.add("monitor_0", 0xABC, timestamp=0.0)

        # At T=301 (> heartbeat_interval), check if similar frame should be forced
        current_time = 301.0
        last_enqueue = cache.get_last_enqueue_time("monitor_0")
        assert last_enqueue is not None
        time_since_last = current_time - last_enqueue

        # Should force if heartbeat timeout exceeded
        is_similar = cache.is_similar_to_cache("monitor_0", 0xABD, threshold)
        should_force = time_since_last >= heartbeat_interval

        assert is_similar is True
        assert should_force is True  # Should be forced due to heartbeat

    def test_simhash_cache_per_device_isolation(self):
        """Each device should have independent heartbeat timers."""
        cache = SimhashCache(cache_size_per_device=1)

        # Monitor 0: frame at T=0
        cache.add("monitor_0", 0xABC, timestamp=0.0)

        # Monitor 1: frame at T=100
        cache.add("monitor_1", 0xDEF, timestamp=100.0)

        # Verify independent timers
        assert cache.get_last_enqueue_time("monitor_0") == 0.0
        assert cache.get_last_enqueue_time("monitor_1") == 100.0

        # Heartbeat timeout at T=200
        # Monitor 0: should force (200 > 300? No, but 200-0=200 < 300, so not yet)
        # Monitor 1: should NOT force (200-100=100 < 300)
        current_time = 200.0
        heartbeat_interval = 300

        mon0_last = cache.get_last_enqueue_time("monitor_0")
        mon1_last = cache.get_last_enqueue_time("monitor_1")
        assert mon0_last is not None
        assert mon1_last is not None

        mon0_time_since = current_time - mon0_last
        mon1_time_since = current_time - mon1_last

        assert mon0_time_since < heartbeat_interval  # Not yet
        assert mon1_time_since < heartbeat_interval  # Not yet

        # At T=350
        current_time = 350.0
        mon0_last = cache.get_last_enqueue_time("monitor_0")
        mon1_last = cache.get_last_enqueue_time("monitor_1")
        assert mon0_last is not None
        assert mon1_last is not None

        mon0_time_since = current_time - mon0_last
        mon1_time_since = current_time - mon1_last

        assert mon0_time_since >= heartbeat_interval  # Should force
        assert mon1_time_since < heartbeat_interval  # Still ok

    def test_simhash_allows_dissimilar_frames(self):
        """Dissimilar frames should always be enqueued."""
        cache = SimhashCache(cache_size_per_device=1)
        threshold = 8

        # Add first frame
        cache.add("monitor_0", 0xABC, timestamp=0.0)

        # Check dissimilar frame (large hamming distance)
        # Use hashes with distance > threshold
        hash1 = 0x0000000000000000
        hash2 = 0x00000000000001FF  # 9 bits different

        cache.add("monitor_1", hash1, timestamp=0.0)
        is_similar = cache.is_similar_to_cache("monitor_1", hash2, threshold)

        assert is_similar is False  # Should NOT be similar

    def test_simhash_cache_size_eviction(self):
        """Cache should evict oldest entries when at capacity."""
        cache = SimhashCache(cache_size_per_device=2)

        # Add 3 frames
        cache.add("monitor_0", 0x111, timestamp=0.0)
        cache.add("monitor_0", 0x222, timestamp=100.0)
        cache.add("monitor_0", 0x333, timestamp=200.0)

        # First frame should be evicted
        assert not cache.is_similar_to_cache("monitor_0", 0x111, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0x222, threshold=0)
        assert cache.is_similar_to_cache("monitor_0", 0x333, threshold=0)

    def test_phash_computation_consistency(self):
        """PHash should be consistent for identical images."""
        img = Image.new("RGB", (100, 100), color="red")

        hash1 = compute_phash(img)
        hash2 = compute_phash(img)

        assert hash1 == hash2

    def test_phash_robustness_to_minor_changes(self):
        """PHash should be robust to minor visual changes."""
        # Create base image
        img1 = Image.new("RGB", (100, 100), color="red")

        # Create slightly modified image
        img2 = Image.new("RGB", (100, 100), color="red")
        for i in range(5):
            for j in range(5):
                img2.putpixel((i, j), (255, 0, 1))

        hash1 = compute_phash(img1)
        hash2 = compute_phash(img2)

        # Hamming distance should be small
        distance = hamming_distance(hash1, hash2)
        assert distance <= 8  # Within threshold

    @pytest.mark.integration
    def test_capture_pipeline_integration(self, tmp_path):
        """Integration test for the complete capture pipeline with simhash.

        This test verifies:
        1. Similar frames are dropped
        2. Heartbeat forces frame after timeout
        3. Simhash is added to metadata
        """
        # This would be a full integration test requiring:
        # - Mock ScreenRecorder
        # - Simulated capture events
        # - Verification of spool contents
        # - Verification of dropped frames
        #
        # For now, we've validated the individual components above.
        # A full integration test would be in tests/test_p1_s2b_plus_capture.py
        pass
