"""Tests for timezone context header injection in chat."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import tempfile


def test_build_timezone_header_has_two_lines():
    """Verify timezone header has exactly 2 lines."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 16, 30, 0, tzinfo=pi_rpc_mod.UTC8)

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    lines = [line for line in header.split("\n") if line.strip()]
    assert len(lines) == 2


def test_build_timezone_header_contains_date():
    """Verify header contains Date line."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 16, 30, 0, tzinfo=pi_rpc_mod.UTC8)

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    assert "Date: 2026-04-02" in header


def test_build_timezone_header_contains_local_time():
    """Verify header contains Local time now line."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 16, 30, 0, tzinfo=pi_rpc_mod.UTC8)

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    assert "Local time now: 2026-04-02T16:30:00" in header


def test_build_timezone_header_no_utc_tokens():
    """Verify header does not contain old UTC conversion tokens."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 16, 30, 0, tzinfo=pi_rpc_mod.UTC8)

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    assert "Local midnight today (UTC)" not in header
    assert "Local midnight yesterday (UTC)" not in header
    assert "Now (UTC)" not in header
    assert "Timezone:" not in header


def test_build_timezone_header_format():
    """Verify header format matches expected 2-line output."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 16, 30, 0, tzinfo=pi_rpc_mod.UTC8)

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    assert header == "Date: 2026-04-02\nLocal time now: 2026-04-02T16:30:00\n"
