from __future__ import annotations

from typing import get_args

from openrecall.client.accessibility.hash import (
    canonicalize_accessibility_text,
    compute_content_hash,
    is_ax_hash_eligible,
    should_dedup,
)
from openrecall.client.accessibility.types import AXOutcome


def test_canonicalize_accessibility_text_normalizes_nfc_newlines_and_whitespace() -> (
    None
):
    raw = "Cafe\u0301\r\nline 1   \rline 2\t\n\n  "

    canonical = canonicalize_accessibility_text(raw)

    assert canonical == "Caf\u00e9\nline 1\nline 2"


def test_compute_content_hash_returns_none_for_empty_canonicalized_text() -> None:
    assert compute_content_hash("  \r\n\t  ") is None


def test_compute_content_hash_returns_sha256_prefixed_hex_for_non_empty_text() -> None:
    content_hash = compute_content_hash("alpha")

    assert content_hash is not None
    assert content_hash.startswith("sha256:")
    assert len(content_hash) == len("sha256:") + 64


def test_ax_hash_eligible_denominator_follows_trimmed_non_empty_rule() -> None:
    assert is_ax_hash_eligible("text") is True
    assert is_ax_hash_eligible("  text  ") is True
    assert is_ax_hash_eligible("\n\t  ") is False
    assert is_ax_hash_eligible(None) is False


def test_should_dedup_condition_matrix_boundaries() -> None:
    same_hash = "sha256:" + "1" * 64

    assert (
        should_dedup(
            capture_trigger="app_switch",
            content_hash=same_hash,
            last_content_hash=same_hash,
            elapsed_seconds=29.9,
            permission_blocked=False,
        )
        is True
    )
    assert (
        should_dedup(
            capture_trigger="app_switch",
            content_hash=same_hash,
            last_content_hash=same_hash,
            elapsed_seconds=30.0,
            permission_blocked=False,
        )
        is False
    )
    assert (
        should_dedup(
            capture_trigger="app_switch",
            content_hash=same_hash,
            last_content_hash=same_hash,
            elapsed_seconds=30.1,
            permission_blocked=False,
        )
        is False
    )
    assert (
        should_dedup(
            capture_trigger="idle",
            content_hash=same_hash,
            last_content_hash=same_hash,
            elapsed_seconds=5.0,
            permission_blocked=False,
        )
        is False
    )
    assert (
        should_dedup(
            capture_trigger="manual",
            content_hash=same_hash,
            last_content_hash=same_hash,
            elapsed_seconds=5.0,
            permission_blocked=False,
        )
        is False
    )
    assert (
        should_dedup(
            capture_trigger="app_switch",
            content_hash=None,
            last_content_hash=same_hash,
            elapsed_seconds=5.0,
            permission_blocked=False,
        )
        is False
    )
    assert (
        should_dedup(
            capture_trigger="app_switch",
            content_hash=same_hash,
            last_content_hash=same_hash,
            elapsed_seconds=5.0,
            permission_blocked=True,
        )
        is False
    )


def test_recorder_outcomes_exclude_schema_rejected() -> None:
    assert "schema_rejected" not in get_args(AXOutcome)
