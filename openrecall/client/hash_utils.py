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
    In-memory cache for storing recent PHash values with per-device isolation.

    Each device (monitor) maintains its own independent cache entry with:
    - Recent PHash values in a sliding window (FIFO eviction)
    - Last successful enqueue timestamp for heartbeat calculation

    Thread Safety: This class is NOT thread-safe. External synchronization
    is required if accessed from multiple threads.

    Attributes:
        cache_size_per_device: Maximum number of hashes to store per device
        _caches: Dictionary mapping device_name -> OrderedDict of (phash, timestamp)
        _last_enqueue_time: Dictionary mapping device_name -> timestamp

    Example:
        >>> cache = SimhashCache(cache_size_per_device=10)
        >>> cache.add("monitor_0", 0xABC, timestamp=100.0)
        >>> cache.get_last_enqueue_time("monitor_0")
        100.0
        >>> cache.is_similar_to_cache("monitor_0", 0xABC, threshold=8)
        True
    """

    def __init__(self, cache_size_per_device: int = 1):
        """
        Initialize the SimhashCache.

        Args:
            cache_size_per_device: Maximum number of recent hashes to store
                                   per device (default: 1)
        """
        self.cache_size_per_device = cache_size_per_device
        self._caches: dict[str, OrderedDict[int, float]] = {}
        self._last_enqueue_time: dict[str, float] = {}

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
        self, device_name: str, phash: int, threshold: int = 8
    ) -> bool:
        """
        Check if a PHash is similar to any cached PHash for a device.

        Args:
            device_name: Device identifier
            phash: 64-bit PHash value to check
            threshold: Maximum Hamming distance for similarity (default: 8 bits)

        Returns:
            True if similar to any cached hash, False otherwise

        Example:
            >>> cache = SimhashCache()
            >>> cache.add("monitor_0", 0xABC, 100.0)
            >>> cache.is_similar_to_cache("monitor_0", 0xABC, threshold=8)
            True
            >>> cache.is_similar_to_cache("monitor_0", 0xFFF, threshold=8)
            False
        """
        if device_name not in self._caches:
            return False

        cache = self._caches[device_name]

        for cached_hash in cache.keys():
            if is_similar(phash, cached_hash, threshold):
                return True

        return False

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

