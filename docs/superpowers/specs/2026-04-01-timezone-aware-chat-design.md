# Timezone-Aware Chat Design

**Date:** 2026-04-01
**Status:** Approved

## Problem

Timestamps in MyRecall are stored as UTC ISO8601 (with `Z` suffix). When a user in UTC+8 asks "what did I do today?", they mean local today (2026-04-02 00:00:00 ~ 23:59:59 local), but the system queries UTC today (2026-04-02 00:00:00 ~ 23:59:59 UTC), missing the 16 hours of activity from the previous day (UTC previous day 16:00:00 ~ 23:59:59).

Screenpipe solves this by: (1) injecting a timezone header into every AI prompt, and (2) SKILL.md references that header for local-time conversions.

## Design Decision

**Follow Screenpipe's approach** — inject timezone context into every chat message in `pi_rpc.py`, update SKILL.md to reference it. No database changes, no API middleware changes.

## Changes

### 1. `openrecall/client/chat/pi_rpc.py`

Add `_build_timezone_header()` function and prepend it to every message in `send_prompt()`.

**Before:**
```python
def send_prompt(self, content: str, images: Optional[list[str]] = None) -> str:
    ...
    cmd = {"type": "prompt", "id": request_id, "message": content}
```

**After:**
```python
def _build_timezone_header(self) -> str:
    """Build timezone context header (mirrors screenpipe's render_prompt_with_port)."""
    now = datetime.now()
    tz_name = now.strftime("%Z")           # e.g. "CST"
    tz_offset = now.strftime("%:z")         # e.g. "+08:00"
    date_str = now.strftime("%Y-%m-%d")

    # Today's local midnight -> UTC
    local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight = local_midnight.astimezone(timezone.utc)
    midnight_utc = utc_midnight.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Yesterday's local midnight -> UTC
    yesterday_midnight = local_midnight - timedelta(days=1)
    yesterday_utc = yesterday_midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return (
        f"Time range: {midnight_utc} to {date_str}T23:59:59Z\n"
        f"Date: {date_str}\n"
        f"Timezone: {tz_name} (UTC{tz_offset})\n"
        f"Local midnight today (UTC): {midnight_utc}\n"
        f"Local midnight yesterday (UTC): {yesterday_utc}\n"
    )

def send_prompt(self, content: str, images: Optional[list[str]] = None) -> str:
    ...
    header = self._build_timezone_header()
    full_message = f"{header}\n{content}"
    cmd = {"type": "prompt", "id": request_id, "message": full_message}
```

**Example injected header (for UTC+8, 2026-04-02 08:30:00 local):**
```
Time range: 2026-04-01T16:00:00Z to 2026-04-02T15:59:59Z
Date: 2026-04-02
Timezone: CST (UTC+08:00)
Local midnight today (UTC): 2026-04-01T16:00:00Z
Local midnight yesterday (UTC): 2026-03-31T16:00:00Z
```

### 2. `openrecall/client/chat/skills/myrecall-search/SKILL.md`

Update **Time Formatting Strategy** section (lines 17-43).

**Changes:**

1. Remove `> **IMPORTANT — Time Format**: All timestamps use **ISO 8601 UTC**. Do NOT use natural language time like "1h ago".` — no longer accurate since we now handle conversion.

2. Add reference to injected timezone context.

3. Update the conversion table:

**Before:**
```markdown
| Expression | Meaning | ISO 8601 Format |
| `today` | Since midnight UTC | `date -u +%Y-%m-%dT%H:%M:%SZ -d "today"` |
| `yesterday` | Yesterday's full day | 00:00 to 23:59:59 UTC |
```

**After:**
```markdown
> **Timezone**: Local timezone context is injected at the start of each message.
> Use the values from that header for local time conversions.

| Expression | Meaning | How to compute |
| `today` | Since midnight LOCAL time | Use `Local midnight today (UTC)` from context above |
| `yesterday` | Yesterday's LOCAL full day | `Local midnight yesterday (UTC)` to `Local midnight today (UTC) - 1s` |
| `recent` | Last 30 min | `now - 30min` (UTC) |
| `1h ago` | One hour ago | `now - 1h` (UTC) |
```

4. Update the example in the table (lines 36-43) to show referencing the header instead of `date -u`.

## What This Solves

- "What did I do today?" → AI uses `Local midnight today (UTC)` = correct UTC range
- "Yesterday" → AI uses `Local midnight yesterday (UTC)` = correct UTC range
- Any local time expression → AI has the conversion anchor from the header

## What This Does NOT Solve

- API direct calls (non-chat) — timestamps in API responses remain UTC. This is out of scope for this change.
- Display timestamps in web UI — separate concern.

## Backward Compatibility

- No changes to database schema
- No changes to API contracts
- SKILL.md is advisory — AI that doesn't read the header will fall back to UTC behavior (same as before)
- Pi agent's default system prompt is unchanged; only the user message is prefixed
