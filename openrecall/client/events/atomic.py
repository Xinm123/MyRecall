"""Atomic integer wrapper for thread-safe hot-reload of interval values."""

from __future__ import annotations

import ctypes


class AtomicInt:
    """Thread-safe atomic integer using ctypes.c_int64.

    Provides lock-free read and write suitable for use in CGEventTap
    callback threads where blocking on locks would cause system lag.

    GIL guarantees visibility of writes across threads for simple
    assignments in CPython.
    """

    def __init__(self, value: int = 0) -> None:
        self._v = ctypes.c_int64(value)

    def get(self) -> int:
        """Atomically read the current value."""
        return self._v.value

    def set(self, value: int) -> None:
        """Atomically write a new value."""
        self._v.value = value

    def __int__(self) -> int:
        return self._v.value
