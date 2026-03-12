from __future__ import annotations

import hashlib
import unicodedata


def canonicalize_accessibility_text(raw_text: str) -> str:
    normalized = unicodedata.normalize("NFC", raw_text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(normalized_lines).strip()


def compute_content_hash(accessibility_text: str | None) -> str | None:
    canonical = canonicalize_accessibility_text(accessibility_text or "")
    if not canonical:
        return None
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_ax_hash_eligible(accessibility_text: str | None) -> bool:
    canonical = canonicalize_accessibility_text(accessibility_text or "")
    return bool(canonical)


def should_dedup(
    *,
    capture_trigger: str,
    content_hash: str | None,
    last_content_hash: str | None,
    elapsed_seconds: float,
    permission_blocked: bool,
) -> bool:
    if permission_blocked:
        return False
    if capture_trigger in {"idle", "manual"}:
        return False
    if content_hash is None:
        return False
    if last_content_hash != content_hash:
        return False
    return elapsed_seconds < 30.0
