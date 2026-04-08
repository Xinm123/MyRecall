"""Unit tests for AtomicInt."""
import threading
import pytest
from openrecall.client.events.atomic import AtomicInt


def test_atomic_int_basic_get_set():
    a = AtomicInt(42)
    assert a.get() == 42
    a.set(100)
    assert a.get() == 100


def test_atomic_int_default_value():
    a = AtomicInt()
    assert a.get() == 0


def test_atomic_int_int_conversion():
    a = AtomicInt(123)
    assert int(a) == 123


def test_atomic_int_cross_thread():
    """Verify that updates from one thread are visible in another."""
    a = AtomicInt(0)
    results = []

    def writer():
        for i in range(100):
            a.set(i)

    def reader():
        for _ in range(100):
            results.append(a.get())

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=reader)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # At least some reads should see updated values (non-zero)
    assert any(v != 0 for v in results)


def test_trigger_debouncer_hot_reload():
    from openrecall.client.events.base import TriggerDebouncer

    d = TriggerDebouncer(1000)  # 1000ms
    now = 10000

    assert d.should_fire("device1", now) is True  # fires at 10000
    assert d.should_fire("device1", now + 500) is False  # debounced (500 < 1000)
    assert d.should_fire("device1", now + 1000) is True  # fires at 11000

    # Hot-reload: update interval to 500ms
    d.update_interval_ms(500)
    # Last fire was at 11000 (from the third should_fire above)
    # With new 500ms interval, need 500ms gap. 11000 + 500 = 11500
    assert d.should_fire("device1", now + 11501) is True  # 11501 - 11000 = 501 >= 500ms


def test_lockfree_debouncer_hot_reload():
    from openrecall.client.events.base import LockFreeDebouncer

    d = LockFreeDebouncer(1000)
    now = 10000

    assert d.should_fire("device1", now) is True
    assert d.should_fire("device1", now + 500) is False

    d.update_interval_ms(200)
    assert d.should_fire("device1", now + 600) is True  # 200ms interval now
