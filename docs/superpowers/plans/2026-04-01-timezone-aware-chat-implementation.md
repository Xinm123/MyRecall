# Timezone-Aware Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject local timezone context into every Pi prompt so "today"/"yesterday" in chat resolve to the user's local time range, not UTC.

**Architecture:** Add `_build_timezone_header()` to `pi_rpc.py` that mirrors screenpipe's header format. Prepend it to every user message. Update SKILL.md to reference injected values instead of hardcoding UTC.

**Tech Stack:** Python (datetime, timezone), no new dependencies.

---

## Task 1: Add `_build_timezone_header()` to `pi_rpc.py`

**Files:**
- Modify: `openrecall/client/chat/pi_rpc.py`

**Reference:** `openrecall/client/chat/pi_rpc.py:170` (`send_prompt` method). The file already imports `datetime` and `timezone` from `datetime` module via `conversation.py`, but needs `timedelta` added.

- [ ] **Step 1: Add import**

In `openrecall/client/chat/pi_rpc.py`, add `timedelta` to the existing `from datetime import` line at the top of the file:

```python
from datetime import datetime, timezone, timedelta
```

Verify line 10 currently reads:
```python
from datetime import datetime, timezone
```

Change it to:
```python
from datetime import datetime, timezone, timedelta
```

- [ ] **Step 2: Add `_build_timezone_header()` method to `PiRpcManager` class**

After the `__init__` method (around line 60), add this new method inside the class:

```python
    def _build_timezone_header(self) -> str:
        """Build timezone context header (mirrors screenpipe's render_prompt_with_port).

        Injects the user's local timezone and midnight anchors so that AI can
        correctly convert local time expressions ("today", "yesterday") to UTC.
        """
        now = datetime.now()
        tz_name = now.strftime("%Z")            # e.g. "CST", "JST"
        tz_offset = now.strftime("%:z")          # e.g. "+08:00", "-05:00"
        date_str = now.strftime("%Y-%m-%d")     # e.g. "2026-04-02"

        # Today's local midnight -> UTC
        local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        midnight_utc = local_midnight.astimezone(timezone.utc)
        midnight_utc_str = midnight_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Yesterday's local midnight -> UTC
        yesterday_midnight = local_midnight - timedelta(days=1)
        yesterday_utc_str = yesterday_midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return (
            f"Time range: {midnight_utc_str} to {date_str}T23:59:59Z\n"
            f"Date: {date_str}\n"
            f"Timezone: {tz_name} (UTC{tz_offset})\n"
            f"Local midnight today (UTC): {midnight_utc_str}\n"
            f"Local midnight yesterday (UTC): {yesterday_utc_str}\n"
        )
```

- [ ] **Step 3: Update `send_prompt()` to prepend header**

In `openrecall/client/chat/pi_rpc.py`, find the `send_prompt` method (line 170) and change:

```python
    def send_prompt(self, content: str, images: Optional[list[str]] = None) -> str:
        """Send a prompt to Pi."""
        if not self.stdin:
            raise RuntimeError("Pi not running")
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        cmd: dict[str, object] = {"type": "prompt", "id": request_id, "message": content}
```

To:

```python
    def send_prompt(self, content: str, images: Optional[list[str]] = None) -> str:
        """Send a prompt to Pi."""
        if not self.stdin:
            raise RuntimeError("Pi not running")
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        header = self._build_timezone_header()
        full_message = f"{header}\n{content}"
        cmd: dict[str, object] = {"type": "prompt", "id": request_id, "message": full_message}
```

- [ ] **Step 4: Verify syntax**

Run: `python -m py_compile openrecall/client/chat/pi_rpc.py`
Expected: no output (success)

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/chat/pi_rpc.py
git commit -m "feat(chat): inject local timezone header into Pi prompts"
```

---

## Task 2: Update SKILL.md Time Formatting Strategy

**Files:**
- Modify: `openrecall/client/chat/skills/myrecall-search/SKILL.md`

**Reference:** `openrecall/client/chat/skills/myrecall-search/SKILL.md` lines 12-43.

This file has two relevant sections to change:
1. The `> **IMPORTANT — Time Format**` callout (line 12-13)
2. The time conversion table (lines 19-28)
3. The example code block (lines 36-43)

- [ ] **Step 1: Replace the IMPORTANT callout and intro text**

Change lines 12-28 (callout + "Always convert..." + table header + `recent` row through `now` row):
```markdown
> **IMPORTANT — Time Format**: All timestamps use **ISO 8601 UTC**. Do NOT use natural language
> time like `"1h ago"`. Always convert to ISO 8601 before making API calls.

## Time Formatting Strategy

Always convert relative time expressions to ISO 8601 UTC before calling the API.

| Expression | Meaning | ISO 8601 Format |
|------------|---------|-----------------|
| `recent` | Last 30 minutes | `date -u +%Y-%m-%dT%H:%M:%SZ -d "30 minutes ago"` |
| `today` | Since midnight UTC | `date -u +%Y-%m-%dT%H:%M:%SZ -d "today"` |
| `yesterday` | Yesterday's full day | 00:00 to 23:59:59 UTC |
| `1h ago` | One hour ago | `date -u +%Y-%m-%dT%H:%M:%SZ -d "1 hour ago"` |
| `2d ago` | Two days ago | `date -u +%Y-%m-%dT%H:%M:%SZ -d "2 days ago"` |
| `now` | Current moment | `date -u +%Y-%m-%dT%H:%M:%SZ` |
```

To:
```markdown
> **Timezone**: The user's local timezone context is injected at the start of every message.
> Use the values from that header to convert local time expressions to UTC.

## Time Formatting Strategy

Use the timezone context injected at the start of each message to convert local time
expressions to UTC before calling the API.

| Expression | Meaning | How to compute |
|------------|---------|----------------|
| `today` | Since midnight LOCAL time | Use `Local midnight today (UTC)` from context above |
| `yesterday` | Yesterday's LOCAL full day | `Local midnight yesterday (UTC)` to `Local midnight today (UTC) - 1s` |
| `recent` | Last 30 minutes | Current UTC time - 30 minutes |
| `1h ago` | One hour ago | Current UTC time - 1 hour |
| `2d ago` | Two days ago | Current UTC time - 2 days |
| `now` | Current moment | Current UTC time |
```

- [ ] **Step 2: Update the example code block**

Change lines 36-43:
```markdown
**Example — user asks "what was I doing today?":**
```bash
# Get today's midnight UTC
START=$(date -u +%Y-%m-%dT00:00:00Z)
# Get current time
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```
```

To:
```markdown
**Example — user asks "what was I doing today?":**
```bash
# Use the injected header values:
# Local midnight today (UTC): 2026-04-01T16:00:00Z  (for UTC+8)
# Now: 2026-04-02T08:30:00Z
START="2026-04-01T16:00:00Z"   # from injected header (replace with actual value)
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # current UTC time
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/chat/skills/myrecall-search/SKILL.md
git commit -m "docs(skill): use local timezone from injected header for today/yesterday"
```

---

## Task 3: Write unit test for `_build_timezone_header()`

**Files:**
- Create: `tests/test_chat_timezone.py`

- [ ] **Step 1: Write the test**

```python
"""Tests for timezone context header injection in chat."""

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import tempfile


def test_build_timezone_header_utc_plus_8():
    """UTC+8 user at 08:30 local -> midnight today = previous day 16:00 UTC."""
    # Mock datetime to return a fixed local time of 2026-04-02 08:30:00 CST (UTC+8)
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            # 2026-04-02 08:30:00 in UTC+8 = 2026-04-02 00:30:00 UTC
            return cls(2026, 4, 2, 8, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    # 2026-04-02 08:30 CST -> local midnight = 2026-04-02 00:00 CST
    # -> UTC = 2026-04-01 16:00 UTC
    assert "Local midnight today (UTC): 2026-04-01T16:00:00Z" in header
    assert "Local midnight yesterday (UTC): 2026-03-31T16:00:00Z" in header
    assert "Timezone: CST (UTC+08:00)" in header
    assert "Date: 2026-04-02" in header


def test_build_timezone_header_utc_minus_5():
    """UTC-5 user at 10:00 local -> midnight today = same day 05:00 UTC."""
    import openrecall.client.chat.pi_rpc as pi_rpc_mod
    import unittest.mock

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 2, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

    with unittest.mock.patch.object(pi_rpc_mod, "datetime", FixedDate):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            manager = pi_rpc_mod.PiRpcManager(
                workspace_dir=Path(td),
                event_callback=lambda e: None,
            )
            header = manager._build_timezone_header()

    # 2026-04-02 10:00 EDT -> local midnight = 2026-04-02 00:00 EDT
    # -> UTC = 2026-04-02 04:00 UTC
    assert "Local midnight today (UTC): 2026-04-02T04:00:00Z" in header
    assert "Local midnight yesterday (UTC): 2026-04-01T04:00:00Z" in header
    assert "Date: 2026-04-02" in header
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_chat_timezone.py -v`
Expected: FAIL on first run (no test file yet)

- [ ] **Step 3: Commit test (failing)**

```bash
git add tests/test_chat_timezone.py
git commit -m "test(chat): add timezone header unit tests"
```

---

## Verification

After all tasks complete, run:
```bash
python -m py_compile openrecall/client/chat/pi_rpc.py
pytest tests/test_chat_timezone.py -v
git log --oneline -3
```

Expected: py_compile silent, all tests pass, two commits visible.
