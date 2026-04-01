"""Tests for timezone context header injection in chat."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import tempfile


def test_build_timezone_header_utc_plus_8():
    """UTC+8 user at 08:30 local -> midnight today = previous day 16:00 UTC."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 8, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    assert "Local midnight today (UTC): 2026-04-01T16:00:00Z" in header
    assert "Local midnight yesterday (UTC): 2026-03-31T16:00:00Z" in header
    assert "Now (UTC): 2026-04-02T00:30:00Z" in header
    assert "Timezone: CST (UTC+08:00)" in header
    assert "Date: 2026-04-02" in header


def test_build_timezone_header_utc_minus_4():
    """UTC-4 (EDT) user at 10:00 local -> midnight today = same day 04:00 UTC."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    # 2026-04-02 10:00 EDT (UTC-4) -> local midnight = 2026-04-02 00:00 EDT
    # -> UTC = 2026-04-02 04:00 UTC
    assert "Local midnight today (UTC): 2026-04-02T04:00:00Z" in header
    assert "Local midnight yesterday (UTC): 2026-04-01T04:00:00Z" in header
    assert "Now (UTC): 2026-04-02T14:00:00Z" in header
    assert "Date: 2026-04-02" in header
