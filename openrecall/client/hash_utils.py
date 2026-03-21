"""
PHash computation utilities for similarity detection.

This module provides perceptual hashing (PHash) functions for detecting
visually similar frames before they are enqueued into the spool.
"""

from collections import OrderedDict
from typing import Optional

import imagehash
from PIL import Image


def compute_phash(image: Image.Image) -> int:
    """
    Compute 64-bit perceptual hash (PHash) from a PIL Image.

    PHash uses DCT (Discrete Cosine Transform) to produce a hash that is
    robust to minor visual changes like compression, brightness adjustments,
    and small UI updates.

    Args:
        image: PIL Image object to hash

    Returns:
        64-bit integer representing the perceptual hash

    Example:
        >>> from PIL import Image
        >>> img = Image.new('RGB', (100, 100), color='red')
        >>> hash_val = compute_phash(img)
        >>> isinstance(hash_val, int)
        True
    """
    hash_obj = imagehash.phash(image, hash_size=8)
    return int(str(hash_obj), 16)  # Convert hex string to int


def hamming_distance(hash1: int, hash2: int) -> int:
    """
    Calculate Hamming distance between two 64-bit hash values.

    Hamming distance is the number of bit positions where the two hashes differ.
    Lower distance indicates higher visual similarity.

    Args:
        hash1: First 64-bit hash value
        hash2: Second 64-bit hash value

    Returns:
        Number of differing bit positions (0-64)

    Example:
        >>> hamming_distance(0xABC, 0xABD)
        1
        >>> hamming_distance(0xABC, 0xABC)
        0
    """
    return (hash1 ^ hash2).bit_count()


def is_similar(hash1: int, hash2: int, threshold: int = 8) -> bool:
    """
    Check if two frames are visually similar based on PHash Hamming distance.

    Args:
        hash1: First 64-bit hash value
        hash2: Second 64-bit hash value
        threshold: Maximum Hamming distance for similarity (default: 8 bits)

    Returns:
        True if Hamming distance is below or equal to threshold (similar)
        False if Hamming distance is above threshold (not similar)

    Example:
        >>> is_similar(0xABC, 0xABC, threshold=8)
        True
        >>> is_similar(0xABC, 0xFFF, threshold=8)
        False
    """
    distance = hamming_distance(hash1, hash2)
    return distance <= threshold


class SimhashCache:
    """
    In-memory cache for storing recent PHash values with per-device isolation and TTL.

    Each device (monitor) maintains its own independent cache entry with:
    - Recent PHash values in a sliding window (FIFO eviction)
    - Last successful enqueue timestamp for heartbeat calculation
    - TTL-based expiration (expired entries don't block similar content)

    Aligns with screenpipe's deduplication behavior:
    - TTL allows similar content to be captured after timeout
    - Threshold of 10 bits for Hamming distance

    Thread Safety: This class is NOT thread-safe. External synchronization
    is required if accessed from multiple threads.

    Attributes:
        cache_size_per_device: Maximum number of hashes to store per device
        ttl_seconds: Time-to-live for cache entries (default: 60s)
        _caches: Dictionary mapping device_name -> OrderedDict of (phash, timestamp)
        _last_enqueue_time: Dictionary mapping device_name -> timestamp
        _hash_hits: Count of exact hash matches (Hash early exit)

    Example:
        >>> cache = SimhashCache(cache_size_per_device=10, ttl_seconds=60.0)
        >>> cache.add("monitor_0", 0xABC, timestamp=100.0)
        >>> cache.get_last_enqueue_time("monitor_0")
        100.0
        >>> cache.is_similar_to_cache("monitor_0", 0xABC, threshold=10)
        True
    """

    DEFAULT_TTL_SECONDS: float = float("inf")  # Default to no expiry for backward compat
    DEFAULT_THRESHOLD: int = 10

    def __init__(
        self,
        cache_size_per_device: int = 1,
        ttl_seconds: float = float("inf"),
    ):
        """
        Initialize the SimhashCache.

        Args:
            cache_size_per_device: Maximum number of recent hashes to store
                                   per device (default: 1)
            ttl_seconds: Time-to-live for cache entries in seconds.
                        After TTL from newest entry, older entries are considered expired.
                        Default is infinity (no expiry) for backward compatibility.
        """
        self.cache_size_per_device = cache_size_per_device
        self.ttl_seconds = ttl_seconds
        self._caches: dict[str, OrderedDict[int, float]] = {}
        self._last_enqueue_time: dict[str, float] = {}
        # Hash early exit statistics
        self._hash_hits: int = 0
        self._total_checks: int = 0

    def add(self, device_name: str, phash: int, timestamp: float) -> None:
        """
        Add a PHash value and its enqueue timestamp to the cache.

        If the cache for this device is full, the oldest entry is evicted (FIFO).

        Args:
            device_name: Device identifier (e.g., "monitor_0")
            phash: 64-bit PHash value
            timestamp: Enqueue timestamp (seconds since epoch)

        Example:
            >>> cache = SimhashCache(cache_size_per_device=2)
            >>> cache.add("monitor_0", 0xABC, 100.0)
            >>> cache.add("monitor_0", 0xDEF, 200.0)
        """
        if device_name not in self._caches:
            self._caches[device_name] = OrderedDict()

        cache = self._caches[device_name]

        if self.cache_size_per_device <= 0:
            self._last_enqueue_time[device_name] = timestamp
            return

        if phash in cache:
            cache.move_to_end(phash)
        elif len(cache) >= self.cache_size_per_device:
            cache.popitem(last=False)

        # Add new entry
        cache[phash] = timestamp

        # Update last enqueue time
        self._last_enqueue_time[device_name] = timestamp

    def get_last_enqueue_time(self, device_name: str) -> Optional[float]:
        """
        Get the timestamp of the last successfully enqueued frame for a device.

        Args:
            device_name: Device identifier

        Returns:
            Timestamp of last enqueue, or None if device has no enqueued frames

        Example:
            >>> cache = SimhashCache()
            >>> cache.get_last_enqueue_time("monitor_0") is None
            True
            >>> cache.add("monitor_0", 0xABC, 100.0)
            >>> cache.get_last_enqueue_time("monitor_0")
            100.0
        """
        return self._last_enqueue_time.get(device_name)

    def is_similar_to_cache(
        self,
        device_name: str,
        phash: int,
        threshold: int = 10,
        current_time: Optional[float] = None,
    ) -> bool:
        """
        Check if a PHash is similar to any cached PHash for a device.

        Uses Hash early exit optimization: if the hash is exactly present in
        the cache, returns True immediately without computing Hamming distance.

        TTL check: Entries older than ttl_seconds from the newest entry are skipped.
        This means the TTL is relative to the most recent capture, ensuring consistent
        behavior in both real-time and test scenarios.

        Args:
            device_name: Device identifier
            phash: 64-bit PHash value to check
            threshold: Maximum Hamming distance for similarity (default: 10 bits)
            current_time: Optional current timestamp for testing. If not provided,
                         uses the max timestamp from cache entries.

        Returns:
            True if similar to any non-expired cached hash, False otherwise

        Example:
            >>> cache = SimhashCache(ttl_seconds=60.0)
            >>> cache.add("monitor_0", 0xABC, timestamp=100.0)
            >>> cache.is_similar_to_cache("monitor_0", 0xABC, threshold=10, current_time=150.0)
            True
            >>> cache.is_similar_to_cache("monitor_0", 0xABC, threshold=10, current_time=200.0)
            False  # TTL expired (>60s from newest entry)
        """
        self._total_checks += 1

        if device_name not in self._caches:
            return False

        cache = self._caches[device_name]
        if not cache:
            return False

        # Use relative TTL: compare against most recent entry timestamp
        # This makes TTL behavior consistent for both real-time and test scenarios
        max_timestamp = max(cache.values())
        if current_time is None:
            current_time = max_timestamp

        # Hash early exit: O(1) check for exact match (if not expired)
        if phash in cache:
            entry_time = cache[phash]
            # TTL is relative to newest entry in cache
            if max_timestamp - entry_time < self.ttl_seconds:
                self._hash_hits += 1
                return True
            # Expired exact match - don't count as hit, continue to fuzzy check

        # No exact match or expired: check Hamming distance against non-expired hashes
        for cached_hash, entry_time in cache.items():
            # TTL check: skip entries older than TTL from newest
            if max_timestamp - entry_time >= self.ttl_seconds:
                continue
            if is_similar(phash, cached_hash, threshold):
                return True

        return False

    def get_stats(self) -> dict[str, int | float]:
        """
        Get hash early exit statistics.

        Returns:
            Dictionary with hash_hits, total_checks, and hit_rate
        """
        hit_rate = (
            self._hash_hits / self._total_checks if self._total_checks > 0 else 0.0
        )
        return {
            "hash_hits": self._hash_hits,
            "total_checks": self._total_checks,
            "hit_rate": round(hit_rate, 4),
        }

    def reset_stats(self) -> None:
        """Reset hash early exit statistics."""
        self._hash_hits = 0
        self._total_checks = 0

    def clear_device(self, device_name: str) -> None:
        """
        Clear the cache for a specific device.

        Args:
            device_name: Device identifier

        Example:
            >>> cache = SimhashCache()
            >>> cache.add("monitor_0", 0xABC, 100.0)
            >>> cache.clear_device("monitor_0")
            >>> cache.get_last_enqueue_time("monitor_0") is None
            True
        """
        if device_name in self._caches:
            del self._caches[device_name]
        if device_name in self._last_enqueue_time:
            del self._last_enqueue_time[device_name]

    def clear(self) -> None:
        """
        Clear all caches for all devices.

        Example:
            >>> cache = SimhashCache()
            >>> cache.add("monitor_0", 0xABC, 100.0)
            >>> cache.add("monitor_1", 0xDEF, 200.0)
            >>> cache.clear()
            >>> cache.get_last_enqueue_time("monitor_0") is None
            True
        """
        self._caches.clear()
        self._last_enqueue_time.clear()

