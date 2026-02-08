"""Tests for smart frame buffer pooling used by monitor pipelines."""

from openrecall.client.sck_stream import FrameBufferPool


def test_pool_allocates_initial_capacity():
    pool = FrameBufferPool(max_bytes=64)
    buf, is_temp = pool.acquire(32)
    assert is_temp is False
    assert len(buf) >= 32
    assert pool.capacity >= 32


def test_pool_expands_to_power_of_two():
    pool = FrameBufferPool(max_bytes=1024)
    pool.acquire(100)
    buf, is_temp = pool.acquire(600)

    assert is_temp is False
    assert len(buf) >= 600
    assert pool.capacity >= 600
    # 1024 is the next power-of-two above 600
    assert pool.capacity == 1024


def test_pool_uses_temporary_buffer_when_above_limit():
    pool = FrameBufferPool(max_bytes=1024)
    pool.acquire(512)

    buf, is_temp = pool.acquire(2048)

    assert is_temp is True
    assert len(buf) == 2048
    # Persistent pool should remain unchanged
    assert pool.capacity == 512
