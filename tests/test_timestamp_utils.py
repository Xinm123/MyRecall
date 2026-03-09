from openrecall.shared.utils import timestamp_to_human_readable


def test_timestamp_to_human_readable_accepts_iso8601() -> None:
    value = timestamp_to_human_readable("2026-03-08T16:00:00Z")
    assert value == "2026-03-08 16:00:00"


def test_timestamp_to_human_readable_accepts_unix_seconds() -> None:
    value = timestamp_to_human_readable(1741434245)
    assert isinstance(value, str)
    assert len(value) == 19


def test_timestamp_to_human_readable_invalid_returns_empty() -> None:
    assert timestamp_to_human_readable("not-a-timestamp") == ""
