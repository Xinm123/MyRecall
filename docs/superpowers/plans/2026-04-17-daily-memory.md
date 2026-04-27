# Daily Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an automatic daily markdown diary feature that summarizes completed frame descriptions into fixed 1-hour segments, appending them incrementally to `~/.myrecall/server/daily_memories/YYYY-MM-DD.md`.

**Architecture:** A `DailyMemoryWorker` runs every 5 minutes, calling `DailyMemoryService` to process closed 1-hour segments. The service queries frames with `description_status='completed'`, aggregates them via a lightweight text-only LLM provider, and appends the summary to the day's Markdown file. State is stored in a single YAML checkpoint file.

**Tech Stack:** Python, SQLite, Flask (app.py), `requests` (OpenAI-compatible API), `threading.Thread`, `PyYAML`

**Prerequisite:** `PyYAML` must be listed in `setup.py` `install_requires`.

---

## File Map

| File | Responsibility |
|------|----------------|
| `openrecall/server/database/frames_store.py` | Add `get_frames_with_descriptions_in_range()` query method |
| `openrecall/server/config_server.py` | Add `[daily_memory]` config fields with fallback to `[description]` then `[ai]`; add `daily_memories_path` and ensure directory creation |
| `openrecall/server/daily_memory/__init__.py` | Package marker |
| `openrecall/server/daily_memory/provider.py` | `DailyMemoryProvider` (text-only OpenAI-compatible) + `get_daily_memory_provider()` |
| `openrecall/server/daily_memory/prompts.py` | Chinese prompt template for segment summarization |
| `openrecall/server/daily_memory/service.py` | `DailyMemoryService`: segment boundary math, prompt building, file append, YAML checkpoint updates |
| `openrecall/server/daily_memory/worker.py` | `DailyMemoryWorker`: 5-minute daemon thread |
| `openrecall/server/app.py` | Start `DailyMemoryWorker` alongside other workers |
| `tests/test_daily_memory_service.py` | Unit tests for segment splitting, timezone, checkpoint logic |
| `tests/test_daily_memory_provider.py` | Unit tests for provider initialization and HTTP fallback |
| `tests/test_daily_memory_worker.py` | Unit tests for worker lifecycle |

---

### Task 1: FramesStore Query Methods

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_daily_memory_service.py` (we'll test the store methods here inline)

- [ ] **Step 1: Add query method to FramesStore**

Add the following method to `FramesStore` (after `get_recent_descriptions` around line 2100):

```python
    def get_frames_with_descriptions_in_range(
        self,
        start: str,
        end: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        """Get frames with completed descriptions within a UTC time range.

        Args:
            start: UTC ISO8601 start timestamp (inclusive)
            end: UTC ISO8601 end timestamp (exclusive)
            conn: Optional existing connection. If None, creates a new one.

        Returns:
            List of dicts with timestamp, app_name, window_name, narrative, summary, tags.
        """
        def _query(c: sqlite3.Connection) -> List[Dict[str, Any]]:
            rows = c.execute(
                """
                SELECT f.timestamp, f.app_name, f.window_name,
                       fd.narrative, fd.summary, fd.tags_json
                FROM frames f
                JOIN frame_descriptions fd ON f.id = fd.frame_id
                WHERE f.timestamp >= ? AND f.timestamp < ?
                  AND f.description_status = 'completed'
                ORDER BY f.timestamp ASC
                """,
                (start, end),
            ).fetchall()
            result = []
            for r in rows:
                try:
                    tags = json.loads(r[5]) if r[5] else []
                except (json.JSONDecodeError, TypeError):
                    tags = []
                result.append({
                    "timestamp": r[0],
                    "app_name": r[1] or "",
                    "window_name": r[2] or "",
                    "narrative": r[3] or "",
                    "summary": r[4] or "",
                    "tags": tags,
                })
            return result

        if conn is not None:
            return _query(conn)

        try:
            with self._connect() as conn:
                return _query(conn)
        except sqlite3.Error as e:
            logger.error("get_frames_with_descriptions_in_range failed: %s", e)
            return []
```

- [ ] **Step 2: Add `get_latest_queryable_timestamp` to FramesStore**

Add after the method from Step 1:

```python
    def get_latest_queryable_timestamp(
        self,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[str]:
        """Get the maximum timestamp of frames with visibility_status='queryable'.

        Args:
            conn: Optional existing connection. If None, creates a new one.

        Returns:
            UTC ISO8601 timestamp string, or None if no queryable frames exist.
        """
        sql = "SELECT MAX(timestamp) FROM frames WHERE visibility_status = 'queryable'"

        def _query(c: sqlite3.Connection) -> Optional[str]:
            row = c.execute(sql).fetchone()
            return row[0] if row and row[0] else None

        if conn is not None:
            return _query(conn)

        try:
            with self._connect() as conn:
                return _query(conn)
        except sqlite3.Error as e:
            logger.error("get_latest_queryable_timestamp failed: %s", e)
            return None
```

- [ ] **Step 3: Verify import of `json` and typing at top of file**

Ensure `import json` exists near the top of `frames_store.py` (it does, line 1). Ensure `Dict` and `Any` are imported from `typing` (add if missing):

```python
from typing import Any, Dict, List, Optional
```

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "feat(daily-memory): add query for completed descriptions and latest queryable timestamp"
```

---

### Task 2: Server Config for daily_memory

**Files:**
- Modify: `openrecall/server/config_server.py`
- Test: `tests/test_config_server.py`

- [ ] **Step 1: Add PyYAML dependency to `setup.py`**

Add `"pyyaml>=6.0"` to the `install_requires` list in `setup.py`.

```python
    "onnxruntime>=1.16.0",  # Explicit ONNX runtime for RapidOCR v3
    "pyyaml>=6.0",
]
```

- [ ] **Step 2: Add fields to ServerSettings and `_from_dict`**

Add to `ServerSettings` class after `fusion_log_enabled`:

```python
    # [daily_memory]
    daily_memory_enabled: bool = True
    daily_memory_provider: str = ""
    daily_memory_model: str = ""
    daily_memory_api_key: str = ""
    daily_memory_api_base: str = ""
```

Add to `_from_dict` after `fusion_log_enabled`:

```python
            daily_memory_enabled=data.get("daily_memory.enabled", True),
            daily_memory_provider=data.get("daily_memory.provider", ""),
            daily_memory_model=data.get("daily_memory.model", ""),
            daily_memory_api_key=data.get("daily_memory.api_key", ""),
            daily_memory_api_base=data.get("daily_memory.api_base", ""),
```

- [ ] **Step 3: Add daily_memories_path property**

Add after `lancedb_path` property:

```python
    @property
    def daily_memories_path(self) -> Path:
        """Path to the daily memories markdown directory."""
        path = self.paths_data_dir / "daily_memories"
        path.mkdir(parents=True, exist_ok=True)
        return path
```

- [ ] **Step 4: Ensure directory creation in `_ensure_dirs()`**

Add inside both the `try` block and the `except PermissionError` fallback block of `_ensure_dirs()`:

```python
            (self.paths_data_dir / "daily_memories").mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 5: Write config test**

Append to `tests/test_config_server.py` (create if missing, otherwise add test):

```python
def test_daily_memory_config_fallback():
    from openrecall.server.config_server import ServerSettings

    data = {
        "description.provider": "openai",
        "description.model": "gpt-4",
        "description.api_key": "sk-desc",
        "description.api_base": "https://api.desc.com/v1",
    }
    settings = ServerSettings._from_dict(data)
    assert settings.daily_memory_enabled is True
    # empty strings should fall back at runtime in get_daily_memory_provider()
    assert settings.daily_memory_provider == ""
```

Run: `pytest tests/test_config_server.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add setup.py openrecall/server/config_server.py tests/test_config_server.py
git commit -m "feat(daily-memory): add server config fields, path property, and pyyaml dep"
```

---

### Task 3: Daily Memory Text-Only Provider

**Files:**
- Create: `openrecall/server/daily_memory/provider.py`
- Create: `openrecall/server/daily_memory/__init__.py`
- Test: `tests/test_daily_memory_provider.py`

- [ ] **Step 1: Create provider module**

```python
"""Text-only LLM provider for daily memory aggregation."""

import logging
import time
from typing import Optional

import requests

from openrecall.server.ai.providers import _normalize_api_base
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class DailyMemoryProviderError(Exception):
    """Base error for daily memory provider."""


class DailyMemoryProviderConfigError(DailyMemoryProviderError):
    """Configuration error."""


class DailyMemoryProviderRequestError(DailyMemoryProviderError):
    """Request error."""


def _resolve_daily_memory_config() -> tuple[str, str, str, str]:
    """Resolve config with fallback: [daily_memory] -> [description] -> [ai]."""
    provider = settings.daily_memory_provider or settings.description_provider or settings.ai_provider
    model = settings.daily_memory_model or settings.description_model or settings.ai_model_name
    api_key = settings.daily_memory_api_key or settings.description_api_key or settings.ai_api_key
    api_base = settings.daily_memory_api_base or settings.description_api_base or settings.ai_api_base
    return provider.strip().lower() if provider else "openai", model, api_key, api_base


class DailyMemoryProvider:
    """Text-only chat provider using OpenAI-compatible HTTP API."""

    def __init__(
        self,
        provider: str,
        model_name: str,
        api_key: str,
        api_base: str,
        request_timeout: int = 120,
    ) -> None:
        if not model_name:
            raise DailyMemoryProviderConfigError("model_name is required")
        self.provider = provider
        self.model_name = model_name.strip()
        self.api_key = api_key.strip() if api_key else ""

        if provider == "local":
            raise DailyMemoryProviderConfigError(
                "daily_memory provider='local' is not supported. "
                "Please configure an API-based provider (openai/dashscope) with api_base and api_key."
            )

        effective_base = api_base
        if not effective_base:
            if provider == "dashscope":
                effective_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            else:
                effective_base = "https://api.openai.com/v1"
        self.api_base = _normalize_api_base(effective_base)
        self.request_timeout = request_timeout

    def generate(self, prompt: str) -> str:
        """Send a text-only chat completion request and return the content string."""
        url = f"{self.api_base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        try:
            start_time = time.time()
            resp = requests.post(url, headers=headers, json=payload, timeout=self.request_timeout)
            elapsed = time.time() - start_time
        except Exception as e:
            raise DailyMemoryProviderRequestError(f"DailyMemory request failed: {e}") from e

        if not resp.ok:
            raise DailyMemoryProviderRequestError(
                f"DailyMemory request failed: status={resp.status_code} body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise DailyMemoryProviderRequestError("choices missing in response")
            message = choices[0].get("message") or {}
            content = message.get("content", "")
        except Exception as e:
            raise DailyMemoryProviderRequestError(f"Parse failed: {e}") from e

        result = content.strip()
        logger.info(f"DailyMemory generated in {elapsed:.2f}s: {len(result)} chars")
        return result


def get_daily_memory_provider() -> DailyMemoryProvider:
    """Get a DailyMemoryProvider using resolved config."""
    provider, model_name, api_key, api_base = _resolve_daily_memory_config()
    return DailyMemoryProvider(
        provider=provider,
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
        request_timeout=settings.ai_request_timeout,
    )
```

- [ ] **Step 2: Create package init**

```python
"""Daily memory package."""
```

- [ ] **Step 3: Write provider test**

```python
"""Tests for DailyMemoryProvider."""

import pytest
from unittest.mock import patch, MagicMock

from openrecall.server.daily_memory.provider import (
    DailyMemoryProvider,
    DailyMemoryProviderConfigError,
    DailyMemoryProviderRequestError,
    get_daily_memory_provider,
)


class TestDailyMemoryProvider:
    def test_missing_model_raises(self):
        with pytest.raises(DailyMemoryProviderConfigError):
            DailyMemoryProvider("openai", "", "", "")

    @patch("openrecall.server.daily_memory.provider.requests.post")
    def test_generate_returns_content(self, mock_post):
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "choices": [{"message": {"content": "  日记内容  "}}]
            },
        )
        provider = DailyMemoryProvider("openai", "gpt-4", "sk-xxx", "https://api.openai.com/v1")
        result = provider.generate("prompt")
        assert result == "日记内容"

    @patch("openrecall.server.daily_memory.provider.requests.post")
    def test_generate_raises_on_non_200(self, mock_post):
        mock_post.return_value = MagicMock(ok=False, text="error")
        provider = DailyMemoryProvider("openai", "gpt-4", "sk-xxx", "https://api.openai.com/v1")
        with pytest.raises(DailyMemoryProviderRequestError):
            provider.generate("prompt")


class TestGetDailyMemoryProvider:
    @patch("openrecall.server.daily_memory.provider.settings")
    def test_fallback_chain(self, mock_settings):
        mock_settings.daily_memory_provider = ""
        mock_settings.daily_memory_model = ""
        mock_settings.daily_memory_api_key = ""
        mock_settings.daily_memory_api_base = ""
        mock_settings.description_provider = "dashscope"
        mock_settings.description_model = "qwen-turbo"
        mock_settings.description_api_key = "sk-desc"
        mock_settings.description_api_base = ""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model_name = "gpt-4"
        mock_settings.ai_api_key = "sk-ai"
        mock_settings.ai_api_base = "https://api.ai.com/v1"
        mock_settings.ai_request_timeout = 60

        provider = get_daily_memory_provider()
        assert provider.provider == "dashscope"
        assert provider.model_name == "qwen-turbo"
        assert provider.api_key == "sk-desc"
        assert provider.api_base == "https://api.ai.com/v1"  # fallback to ai base because desc base is empty
```

Run: `pytest tests/test_daily_memory_provider.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/daily_memory/__init__.py openrecall/server/daily_memory/provider.py tests/test_daily_memory_provider.py
git commit -m "feat(daily-memory): add text-only LLM provider with config fallback"
```

---

### Task 4: Prompt Template

**Files:**
- Create: `openrecall/server/daily_memory/prompts.py`
- Test: `tests/test_daily_memory_service.py`

- [ ] **Step 1: Create prompts module**

```python
"""Prompt templates for daily memory generation."""

from datetime import datetime, timezone
from typing import Any, Dict, List


SEGMENT_SUMMARY_PROMPT = """你是一位擅长整理用户数字生活日记的助手。请根据以下时间段内的屏幕截图描述，写一段简洁、连贯的日记总结。

日期：{date}
时间段：{time_range}
总帧数：{frame_count}

帧记录：
{frames_text}

要求：
- 用一段连贯的中文自然语言描述，150-300 字
- 突出主要活动（使用时间最长的应用）
- 提到应用切换和主题变化
- 按时间顺序叙述
- 不要列出每个帧的细节，进行适当的合并与概括
"""


def format_frame_line(
    timestamp_local: str,
    app_name: str,
    summary: str,
    narrative: str,
    tags: List[str],
) -> str:
    """Format a single frame for the prompt."""
    tag_str = ", ".join(tags) if tags else "无"
    return (
        f"[{timestamp_local}] {app_name} | {summary} | {narrative} | tags: {tag_str}"
    )


def _local_tz():
    """MVP: use system local timezone."""
    return datetime.now(timezone.utc).astimezone().tzinfo


def build_segment_prompt(
    date: str,
    time_range: str,
    frames: List[Dict[str, Any]],
) -> str:
    """Build the LLM prompt for a time segment.

    Args:
        date: Local date string, e.g. "2026-04-17"
        time_range: Local time range string, e.g. "10:00 - 11:00"
        frames: List of frame dicts from get_frames_with_descriptions_in_range
    """
    if not frames:
        return ""

    lines = []
    for f in frames:
        # timestamp is UTC ISO8601 like "2026-04-17T10:02:00Z"
        ts = f["timestamp"]
        # Convert UTC to local HH:MM for the prompt
        if len(ts) >= 16:
            dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_part = dt_utc.astimezone(_local_tz()).strftime("%H:%M")
        else:
            time_part = "--:--"
        lines.append(
            format_frame_line(
                timestamp_local=time_part,
                app_name=f["app_name"] or "未知应用",
                summary=f["summary"] or "",
                narrative=f["narrative"] or "",
                tags=f["tags"],
            )
        )

    return SEGMENT_SUMMARY_PROMPT.format(
        date=date,
        time_range=time_range,
        frame_count=len(frames),
        frames_text="\n".join(lines),
    )
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/server/daily_memory/prompts.py
git commit -m "feat(daily-memory): add segment summary prompt template"
```

---

### Task 5: DailyMemoryService

**Files:**
- Create: `openrecall/server/daily_memory/service.py`
- Test: `tests/test_daily_memory_service.py`

- [ ] **Step 1: Create service module**

```python
"""Daily memory service: segment splitting, LLM aggregation, file append."""

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.daily_memory.provider import DailyMemoryProvider, get_daily_memory_provider
from openrecall.server.daily_memory.prompts import build_segment_prompt
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _local_tz() -> timezone:
    """MVP: use system local timezone."""
    return datetime.now().astimezone().tzinfo


def _utc_to_local(dt: datetime) -> datetime:
    return dt.astimezone(_local_tz())


def _local_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_local_tz())
    return dt.astimezone(timezone.utc)


class DailyMemoryService:
    """Service for generating daily memory markdown segments."""

    def __init__(
        self,
        store: Optional[FramesStore] = None,
        provider: Optional[DailyMemoryProvider] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        self._store = store or FramesStore()
        self._provider = provider
        self._output_dir = output_dir or settings.daily_memories_path

    @property
    def provider(self) -> DailyMemoryProvider:
        if self._provider is None:
            self._provider = get_daily_memory_provider()
        return self._provider

    @property
    def _checkpoints_path(self) -> Path:
        return self._output_dir / "checkpoints.yaml"

    def _load_checkpoints(self) -> Dict[str, str]:
        """Load checkpoints.yaml. Returns {date_iso: segment_end_utc_iso}."""
        path = self._checkpoints_path
        if not path.exists():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.warning(f"Failed to load checkpoints.yaml: {e}")
            return {}
        return data if isinstance(data, dict) else {}

    def _save_checkpoints(self, checkpoints: Dict[str, str]) -> None:
        """Atomic write checkpoints.yaml."""
        path = self._checkpoints_path
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(yaml.safe_dump(checkpoints, sort_keys=True, allow_unicode=True), encoding="utf-8")
            tmp.replace(path)
        except Exception as e:
            logger.error(f"Failed to save checkpoints.yaml: {e}")
            raise

    def _get_checkpoint(self, local_date: date) -> Optional[str]:
        """Get segment_end for a given date. Returns UTC ISO8601 string."""
        return self._load_checkpoints().get(local_date.isoformat())

    def _update_checkpoint(self, local_date: date, end_time_utc: datetime) -> None:
        """Update segment_end for a given date."""
        checkpoints = self._load_checkpoints()
        checkpoints[local_date.isoformat()] = end_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        self._save_checkpoints(checkpoints)

    def _md_path(self, local_date: date) -> Path:
        return self._output_dir / f"{local_date.isoformat()}.md"

    def _ensure_md_header(self, md_path: Path, local_date: date) -> None:
        if not md_path.exists():
            md_path.write_text(f"# {local_date.isoformat()}\n\n", encoding="utf-8")

    def _append_segment(self, md_path: Path, local_start: datetime, local_end: datetime, summary: str) -> None:
        time_range = f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}"
        block = f"## {time_range}\n\n{summary}\n\n"
        with open(md_path, "a", encoding="utf-8") as f:
            f.write(block)

    def _generate_segment_summary(self, frames: List[Dict[str, Any]], local_date: date, local_start: datetime, local_end: datetime) -> str:
        if not frames:
            return "无活动记录。"
        time_range = f"{local_start.strftime('%H:%M')} - {local_end.strftime('%H:%M')}"
        prompt = build_segment_prompt(
            date=local_date.isoformat(),
            time_range=time_range,
            frames=frames,
        )
        return self.provider.generate(prompt)

    def process_daily_memory(self, local_date: date) -> None:
        """Process all closed segments for a given local date."""
        now_utc = datetime.now(timezone.utc)

        checkpoint_end = self._get_checkpoint(local_date)
        if checkpoint_end is None:
            day_start_local = datetime.combine(local_date, datetime.min.time()).replace(tzinfo=_local_tz())
            start_time = _local_to_utc(day_start_local)
        else:
            start_time = datetime.fromisoformat(checkpoint_end.replace("Z", "+00:00"))

        # Must wait for the next full hour to end
        if now_utc < start_time + timedelta(hours=1):
            return

        # Query latest queryable frame timestamp from database (realtime)
        latest_queryable_str = self._store.get_latest_queryable_timestamp()
        if latest_queryable_str is None:
            # No queryable frames at all, skip
            return
        latest_queryable = datetime.fromisoformat(latest_queryable_str.replace("Z", "+00:00"))

        # Cap at local midnight to avoid cross-day leakage when recovering past dates
        day_end_local = datetime.combine(local_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=_local_tz())
        day_end_utc = _local_to_utc(day_end_local)

        current_start_utc = start_time
        md_path = self._md_path(local_date)
        self._ensure_md_header(md_path, local_date)

        while (
            current_start_utc + timedelta(hours=1) <= now_utc
            and current_start_utc + timedelta(hours=1) <= day_end_utc
        ):
            segment_end_utc = current_start_utc + timedelta(hours=1)

            # Closure check: segment is only ready when all frames in the segment
            # are queryable (visibility_status='queryable')
            if latest_queryable < segment_end_utc:
                return

            # Query frames (short-lived DB connection)
            frames = self._store.get_frames_with_descriptions_in_range(
                start=current_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end=segment_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

            local_start = _utc_to_local(current_start_utc)
            local_end = _utc_to_local(segment_end_utc)

            if not frames:
                summary = "无活动记录。"
                self._append_segment(md_path, local_start, local_end, summary)
                self._update_checkpoint(local_date, segment_end_utc)
                current_start_utc = segment_end_utc
                continue

            # If all frames lack description content, skip writing but advance checkpoint
            has_content = any((f.get("narrative") or f.get("summary")) for f in frames)
            if not has_content:
                self._update_checkpoint(local_date, segment_end_utc)
                current_start_utc = segment_end_utc
                continue

            try:
                summary = self._generate_segment_summary(frames, local_date, local_start, local_end)
            except Exception as e:
                logger.warning(f"DailyMemory LLM failed for {local_date} {local_start}-{local_end}: {e}")
                # Do not write, do not advance checkpoint — retry next cycle
                return

            self._append_segment(md_path, local_start, local_end, summary)
            self._update_checkpoint(local_date, segment_end_utc)
            current_start_utc = segment_end_utc
```

- [ ] **Step 2: Write service unit tests**

```python
"""Tests for DailyMemoryService."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openrecall.server.daily_memory.service import DailyMemoryService, _local_to_utc, _utc_to_local


class TestTimeHelpers:
    def test_utc_local_roundtrip(self):
        dt_utc = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)
        local = _utc_to_local(dt_utc)
        back = _local_to_utc(local)
        assert back == dt_utc


class TestDailyMemoryService:
    def test_process_empty_segment_writes_placeholder(self, tmp_path):
        mock_store = MagicMock()
        mock_store.get_latest_queryable_timestamp.return_value = "2026-04-17T12:00:00Z"
        mock_store.get_frames_with_descriptions_in_range.return_value = []

        service = DailyMemoryService(store=mock_store, output_dir=tmp_path)

        with patch("openrecall.server.daily_memory.service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            service.process_daily_memory(date(2026, 4, 17))

        md_path = tmp_path / "2026-04-17.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "无活动记录。" in content

        # Verify checkpoint was written
        cp = service._load_checkpoints()
        assert cp.get("2026-04-17") == "2026-04-17T10:00:00Z"

    def test_process_skips_when_latest_queryable_before_segment_end(self, tmp_path):
        """If latest_queryable is before segment_end, the segment should not be processed."""
        mock_store = MagicMock()
        mock_store.get_latest_queryable_timestamp.return_value = "2026-04-17T10:05:00Z"
        # Should not be called because segment is not ready
        mock_store.get_frames_with_descriptions_in_range.return_value = []

        service = DailyMemoryService(store=mock_store, output_dir=tmp_path)

        with patch("openrecall.server.daily_memory.service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 17, 18, 0, 0, tzinfo=timezone.utc)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            service.process_daily_memory(date(2026, 4, 17))

        md_path = tmp_path / "2026-04-17.md"
        # No content written because segment 10:00-11:00 is blocked
        assert not md_path.exists() or "##" not in md_path.read_text(encoding="utf-8")

        cp = service._load_checkpoints()
        assert "2026-04-17" not in cp

    def test_process_skips_when_all_frames_no_description(self, tmp_path):
        mock_store = MagicMock()
        mock_store.get_latest_queryable_timestamp.return_value = "2026-04-17T12:00:00Z"
        mock_store.get_frames_with_descriptions_in_range.return_value = [
            {"timestamp": "2026-04-17T10:05:00Z", "app_name": "X", "summary": "", "narrative": "", "tags": []},
        ]

        service = DailyMemoryService(store=mock_store, output_dir=tmp_path)

        with patch("openrecall.server.daily_memory.service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            service.process_daily_memory(date(2026, 4, 17))

        md_path = tmp_path / "2026-04-17.md"
        content = md_path.read_text(encoding="utf-8")
        assert "##" not in content  # no segment written

        cp = service._load_checkpoints()
        assert cp.get("2026-04-17") == "2026-04-17T10:00:00Z"

    def test_llm_failure_does_not_advance_checkpoint(self, tmp_path):
        mock_store = MagicMock()
        mock_store.get_latest_queryable_timestamp.return_value = "2026-04-17T12:00:00Z"
        mock_store.get_frames_with_descriptions_in_range.return_value = [
            {"timestamp": "2026-04-17T10:05:00Z", "app_name": "X", "summary": "s", "narrative": "n", "tags": ["t"]},
        ]

        mock_provider = MagicMock()
        mock_provider.generate.side_effect = Exception("LLM timeout")

        service = DailyMemoryService(store=mock_store, provider=mock_provider, output_dir=tmp_path)

        with patch("openrecall.server.daily_memory.service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min
            service.process_daily_memory(date(2026, 4, 17))

        md_path = tmp_path / "2026-04-17.md"
        content = md_path.read_text(encoding="utf-8")
        assert "##" not in content

        cp = service._load_checkpoints()
        assert "2026-04-17" not in cp

    def test_checkpoint_yaml_atomic_write(self, tmp_path):
        service = DailyMemoryService(store=MagicMock(), output_dir=tmp_path)
        service._update_checkpoint(date(2026, 4, 17), datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc))
        assert service._get_checkpoint(date(2026, 4, 17)) == "2026-04-17T10:00:00Z"
        assert (tmp_path / "checkpoints.yaml").exists()
```

Run: `pytest tests/test_daily_memory_service.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/daily_memory/service.py tests/test_daily_memory_service.py
git commit -m "feat(daily-memory): add DailyMemoryService with realtime queryable closure check"
```

---

### Task 6: DailyMemoryWorker

**Files:**
- Create: `openrecall/server/daily_memory/worker.py`
- Test: `tests/test_daily_memory_worker.py`

- [ ] **Step 1: Create worker module**

```python
"""Background worker for daily memory generation."""

import logging
import threading
import time
from datetime import date, timedelta
from typing import Optional

from openrecall.server.daily_memory.service import DailyMemoryService
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 300.0  # 5 minutes


class DailyMemoryWorker(threading.Thread):
    """Background worker that processes daily memory segments every 5 minutes."""

    def __init__(self, poll_interval: float = _POLL_INTERVAL):
        super().__init__(daemon=True, name="DailyMemoryWorker")
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._service: Optional[DailyMemoryService] = None

    @property
    def service(self) -> DailyMemoryService:
        if self._service is None:
            self._service = DailyMemoryService()
        return self._service

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("DailyMemoryWorker started")
        while not self._stop_event.is_set():
            try:
                today = date.today()
                # Cross-day recovery: also process yesterday in case server was down overnight
                self.service.process_daily_memory(today - timedelta(days=1))
                self.service.process_daily_memory(today)
            except Exception as e:
                logger.error(f"Unexpected error in DailyMemoryWorker loop: {e}")
            self._stop_event.wait(timeout=self._poll_interval)
        logger.info("DailyMemoryWorker stopped")
```

- [ ] **Step 2: Write worker tests**

```python
"""Tests for DailyMemoryWorker."""

from unittest.mock import MagicMock, patch

from openrecall.server.daily_memory.worker import DailyMemoryWorker


class TestDailyMemoryWorker:
    def test_worker_starts_and_stops(self):
        worker = DailyMemoryWorker(poll_interval=0.1)
        assert worker.name == "DailyMemoryWorker"
        assert worker.daemon is True

    def test_worker_stop_event(self):
        worker = DailyMemoryWorker(poll_interval=0.1)
        assert not worker._stop_event.is_set()
        worker.stop()
        assert worker._stop_event.is_set()

    @patch("openrecall.server.daily_memory.worker.DailyMemoryService")
    def test_run_loop_calls_process(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        worker = DailyMemoryWorker(poll_interval=60.0)
        worker.start()
        # Allow thread to enter loop body once
        import time
        time.sleep(0.01)
        worker.stop()
        worker.join(timeout=1.0)

        assert mock_service.process_daily_memory.called
```

Run: `pytest tests/test_daily_memory_worker.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/daily_memory/worker.py tests/test_daily_memory_worker.py
git commit -m "feat(daily-memory): add DailyMemoryWorker daemon thread"
```

---

### Task 7: Wire Up in app.py

**Files:**
- Modify: `openrecall/server/app.py`
- Test: `tests/test_p1_s1_startup.py` (or create a simple integration check)

- [ ] **Step 1: Start DailyMemoryWorker in init_background_worker**

Add after the DescriptionWorker block in `init_background_worker` (around line 176):

```python
    # Step 5: Start DailyMemoryWorker
    if settings.daily_memory_enabled:
        from openrecall.server.daily_memory.worker import DailyMemoryWorker

        daily_memory_worker = DailyMemoryWorker()
        daily_memory_worker.start()
        app_instance.daily_memory_worker = daily_memory_worker
        logger.info("DailyMemoryWorker started")
```

- [ ] **Step 2: Verify import structure**

No circular imports should exist because `daily_memory/worker.py` only imports `service.py`, which imports `frames_store.py` and `provider.py` — none of which import `app.py`.

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/app.py
git commit -m "feat(daily-memory): start DailyMemoryWorker on server boot"
```

---

### Task 8: Update server.toml.example

**Files:**
- Modify: `server.toml.example`

- [ ] **Step 1: Add daily_memory section to template**

Add at the end of the file:

```toml
# ==============================================================================
# Daily Memory Settings
# ==============================================================================
[daily_memory]
enabled = true               # Enable daily memory generation
provider = ""                # Options: openai, dashscope (local is not supported for daily memory)
model = ""                   # Model name (empty = fallback to [description])
api_key = ""                 # API key (empty = fallback to [description])
api_base = ""                # Base URL (empty = fallback to [description])
```

- [ ] **Step 2: Commit**

```bash
git add server.toml.example
git commit -m "docs: add daily_memory config section to server.toml.example"
```

---

## Spec Coverage Checklist

| Spec Requirement | Plan Task |
|------------------|-----------|
| `~/.myrecall/server/daily_memories/YYYY-MM-DD.md` storage | Task 2 (path property), Task 5 (file write) |
| `checkpoints.yaml` atomic file checkpoint | Task 5 |
| Fixed 1h segments, whole-hour aligned | Task 5 (hourly while loop with day_end_utc boundary) |
| Restart recovery via checkpoint | Task 5 (read checkpoint, resume from last_processed_end_time) |
| Empty segment → "无活动记录。" | Task 5 (empty frames branch) |
| All frames no description → skip write, advance checkpoint | Task 5 (has_content check) |
| LLM failure → no write, no advance, retry next cycle | Task 5 (try/except around generate) |
| Realtime `latest_queryable` closure check | Task 1 (get_latest_queryable_timestamp), Task 5 (process_daily_memory) |
| Delayed upload compat: segment waits until all frames queryable | Task 5 (latest_queryable < segment_end_utc guard) |
| Prompt includes timestamp, app_name, summary, narrative, tags | Task 4, Task 5 |
| Independent `[daily_memory]` config with fallback | Task 2, Task 3 |
| Worker every 5 minutes | Task 6 |
| Local timezone display, UTC checkpoint storage | Task 5 (_local_to_utc, _utc_to_local) |
| No SQLite migration required | Removed Task 1, implemented in Task 5 via YAML |

No placeholders or TBDs remain. All tasks are bite-sized and include exact code, commands, and expected output.
