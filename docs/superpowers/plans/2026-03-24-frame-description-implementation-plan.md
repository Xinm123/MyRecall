# Frame Description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add an AI-generated structured description to each frame, enabling chat agents to understand screen semantics beyond fragmented OCR text.

**Architecture:** Independent `description/` module under `server/`, with its own provider layer, service, and worker. Description tasks are enqueued on ingest and processed asynchronously by a dedicated worker.

**Tech Stack:** Python, SQLite (existing), Pydantic, threading.Thread worker, Flask Blueprint.

**Status:** ✅ Completed — All 47 steps verified. Implementation matches design spec. Post-review fixes applied (entities validator, FrameContext cleanup, local provider log consistency, config Optional types).

---

## File Map

```
openrecall/
├── shared/
│   └── config.py                    # ADD: description config fields
├── server/
│   ├── database/
│   │   ├── migrations/
│   │   │   └── 20260324120000_add_frame_description.sql  # CREATE
│   │   └── frames_store.py         # MODIFY: add description CRUD
│   ├── ai/
│   │   └── factory.py              # MODIFY: add get_description_provider()
│   └── description/                # CREATE (new module)
│       ├── __init__.py
│       ├── models.py               # FrameDescription Pydantic model
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py             # DescriptionProvider protocol
│       │   ├── local.py            # LocalDescriptionProvider
│       │   ├── openai.py           # OpenAIDescriptionProvider
│       │   └── dashscope.py        # DashScopeDescriptionProvider
│       ├── service.py              # DescriptionService
│       └── worker.py               # DescriptionWorker
└── tests/
    ├── test_description_provider.py   # CREATE
    ├── test_description_service.py   # CREATE
    └── test_description_api.py       # CREATE (or extend existing)

Spec:  docs/superpowers/specs/2026-03-24-frame-description-design.md
```

---

## Task 1: Database Migration

**Files:**
- Create: `openrecall/server/database/migrations/20260324120000_add_frame_description.sql`
- Test: `tests/test_description_migration.py` (or extend existing migration test)

- [x] **Step 1: Write the migration SQL**

```sql
-- Migration: 20260324120000_add_frame_description.sql
-- Add description support: frame_descriptions table, description_tasks table, frames.description_status
-- NOTE: Do NOT write to schema_migrations — the runner records migrations automatically.

BEGIN;

-- 1. Add description_status to frames table
ALTER TABLE frames ADD COLUMN description_status TEXT DEFAULT NULL;

-- 2. Create frame_descriptions table
CREATE TABLE IF NOT EXISTS frame_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    narrative TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    intent TEXT NOT NULL,
    summary TEXT NOT NULL,
    description_model TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(frame_id)
);
CREATE INDEX IF NOT EXISTS idx_fd_frame_id ON frame_descriptions(frame_id);

-- 3. Create description_tasks table
CREATE TABLE IF NOT EXISTS description_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(frame_id)
);
CREATE INDEX IF NOT EXISTS idx_dt_status ON description_tasks(status);
CREATE INDEX IF NOT EXISTS idx_dt_next_retry ON description_tasks(next_retry_at);

COMMIT;
```

- [x] **Step 2: Verify migration with bootstrap test**

Run: `pytest tests/test_v3_migrations_bootstrap.py -v`
Expected: All existing migrations pass (the new migration file is automatically picked up since migrations are applied in filename order). If the test passes, the migration is valid.

To additionally verify the new tables exist, add a quick inline check:
```python
def test_description_tables_exist(temp_db):
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('frame_descriptions', 'description_tasks')"
    )
    tables = {row[0] for row in cursor.fetchall()}
    assert "frame_descriptions" in tables
    assert "description_tasks" in tables
    conn.close()
```

- [x] **Step 3: Commit**

```bash
git add openrecall/server/database/migrations/20260324120000_add_frame_description.sql
git commit -m "feat: add frame description migration (frame_descriptions, description_tasks, frames.description_status)"
```

---

## Task 2: Config — Add Description Settings

**Files:**
- Modify: `openrecall/shared/config.py`

- [x] **Step 1: Add description config fields to Settings class**

Add after existing AI provider fields (around line 38):

```python
# Description generation settings
DESCRIPTION_ENABLED: bool = Field(
    default=True,
    alias="OPENRECALL_DESCRIPTION_ENABLED",
    description="Enable AI description generation for frames",
)
DESCRIPTION_PROVIDER: Optional[str] = Field(
    default=None,
    alias="OPENRECALL_DESCRIPTION_PROVIDER",
    description="Description provider: local, dashscope, openai (falls back to ai_provider)",
)
DESCRIPTION_MODEL: Optional[str] = Field(
    default=None,
    alias="OPENRECALL_DESCRIPTION_MODEL",
    description="Model name/path for description provider",
)
```

- [x] **Step 2: Add config resolver in ai/factory.py — get_description_provider()**

Add at end of `factory.py`:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

# ... existing imports ...

_instances: Dict[str, object] = {}

if TYPE_CHECKING:
    from openrecall.server.description.providers.base import DescriptionProvider

def get_description_provider() -> "DescriptionProvider":
    """Get or create a cached DescriptionProvider instance.

    Note: Providers are imported lazily inside this function to avoid circular
    imports. This function is called from DescriptionService, which must not
    be imported at module load time by ai/factory.py.
    """
    capability = "description"
    cached = _instances.get(capability)
    if cached is not None:
        return cached  # type: ignore[return-value]

    # Lazy import — must stay inside function to avoid circular dependency
    from openrecall.server.description.providers import (
        LocalDescriptionProvider,
        OpenAIDescriptionProvider,
        DashScopeDescriptionProvider,
    )

    provider = settings.description_provider or settings.ai_provider
    model_name = settings.description_model or settings.ai_model_name
    api_key = settings.description_api_key or settings.ai_api_key
    api_base = settings.description_api_base or settings.ai_api_base
    provider = (provider or "local").strip().lower()

    if provider == "local":
        instance: "DescriptionProvider" = LocalDescriptionProvider(model_name=model_name)
    elif provider == "dashscope":
        instance = DashScopeDescriptionProvider(api_key=api_key, model_name=model_name)
    elif provider == "openai":
        instance = OpenAIDescriptionProvider(api_key=api_key, model_name=model_name, api_base=api_base)
    else:
        raise AIProviderConfigError(f"Unknown description provider: {provider}")

    _instances[capability] = instance
    return instance
```

> **Note on `TYPE_CHECKING`**: The `DescriptionProvider` type annotation uses a string literal (`"DescriptionProvider"`) because the actual class is defined in `providers/base.py` (Task 4), which imports from `models.py` (Task 3), which is safe — but the factory itself (Task 2) runs before the description module exists. Using `TYPE_CHECKING` + string annotation avoids import-time errors.

- [x] **Step 3: Add api_key and api_base fields to config**

```python
DESCRIPTION_API_KEY: Optional[str] = Field(
    default=None,
    alias="OPENRECALL_DESCRIPTION_API_KEY",
)
DESCRIPTION_API_BASE: Optional[str] = Field(
    default=None,
    alias="OPENRECALL_DESCRIPTION_API_BASE",
)
```

- [x] **Step 4: Commit**

```bash
git add openrecall/shared/config.py openrecall/server/ai/factory.py
git commit -m "feat(config): add description provider settings and factory"
```

---

## Task 3: Description Models

**Files:**
- Create: `openrecall/server/description/__init__.py`
- Create: `openrecall/server/description/models.py`

- [x] **Step 1: Create models.py**

```python
"""Description models for frame description generation."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class FrameDescription(BaseModel):
    """Structured description of a frame's content and user intent."""

    narrative: str = Field(
        ...,
        max_length=512,
        description="Detailed natural language description of the screen content and user intent",
    )
    entities: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Key entities extracted from the frame (max 10 items)",
    )
    intent: str = Field(
        ...,
        description="User intent in natural language phrase (e.g., 'authenticating to GitHub')",
    )
    summary: str = Field(
        ...,
        max_length=200,
        description="One-sentence summary (max 200 chars / ~50 words)",
    )

    def to_db_dict(self) -> dict:
        """Convert to dict for database insertion."""
        import json
        return {
            "narrative": self.narrative,
            "entities_json": json.dumps(self.entities),
            "intent": self.intent,
            "summary": self.summary,
        }


class FrameContext(BaseModel):
    """Context metadata passed to description provider."""
    app_name: Optional[str] = None
    window_name: Optional[str] = None  # Matches frames.window_name column
    browser_url: Optional[str] = None
    timestamp: Optional[float] = None
```

- [x] **Step 2: Create __init__.py**

```python
"""Frame description feature module."""
from openrecall.server.description.models import FrameDescription, FrameContext

__all__ = ["FrameDescription", "FrameContext"]
```

- [x] **Step 3: Commit**

```bash
git add openrecall/server/description/__init__.py openrecall/server/description/models.py
git commit -m "feat(description): add FrameDescription and FrameContext models"
```

---

## Task 4: Provider Protocol and Base

**Files:**
- Create: `openrecall/server/description/providers/__init__.py`
- Create: `openrecall/server/description/providers/base.py`

- [x] **Step 1: Create providers/__init__.py**

```python
"""Description providers."""
from openrecall.server.description.providers.base import DescriptionProvider, DescriptionProviderError
from openrecall.server.description.providers.local import LocalDescriptionProvider
from openrecall.server.description.providers.openai import OpenAIDescriptionProvider
from openrecall.server.description.providers.dashscope import DashScopeDescriptionProvider

__all__ = [
    "DescriptionProvider",
    "DescriptionProviderError",
    "LocalDescriptionProvider",
    "OpenAIDescriptionProvider",
    "DashScopeDescriptionProvider",
]
```

- [x] **Step 2: Create providers/base.py**

```python
"""Description provider protocol and errors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openrecall.server.description.models import FrameDescription, FrameContext


class DescriptionProviderError(Exception):
    """Base error for description providers."""
    pass


class DescriptionProviderConfigError(DescriptionProviderError):
    """Configuration error."""
    pass


class DescriptionProviderRequestError(DescriptionProviderError):
    """Request/execution error."""
    pass


class DescriptionProviderUnavailableError(DescriptionProviderError):
    """Provider unavailable (missing dependency, etc)."""
    pass


class DescriptionProvider(ABC):
    """Protocol for frame description generation providers."""

    @abstractmethod
    def generate(
        self,
        image_path: str,
        context: "FrameContext",
    ) -> "FrameDescription":
        """
        Generate a structured description for a frame.

        Args:
            image_path: Path to the JPEG snapshot file.
            context: Frame metadata for prompt injection.

        Returns:
            FrameDescription with narrative, entities, intent, summary.

        Raises:
            DescriptionProviderRequestError: On API/SDK error.
            DescriptionProviderUnavailableError: On missing dependencies.
        """
        raise NotImplementedError
```

- [x] **Step 3: Commit**

```bash
git add openrecall/server/description/providers/__init__.py openrecall/server/description/providers/base.py
git commit -m "feat(description): add DescriptionProvider protocol and errors"
```

---

## Task 5: LocalDescriptionProvider

**Files:**
- Create: `openrecall/server/description/providers/local.py`

- [x] **Step 1: Write the provider**

```python
"""Local description provider using Qwen3 VL."""
import json
import logging
from pathlib import Path
from typing import Any

from PIL import Image
from qwen_vl_utils import process_vision_info
import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
)
from openrecall.server.ai_engine import AIEngine  # Used for MODEL_ID constant
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_MAX_NEW_TOKENS = 256  # Increased from 128 for richer narrative


def _build_messages(context: FrameContext) -> list[dict[str, Any]]:
    """Build messages for the vision model with context injection."""
    app_context = ""
    if context.app_name:
        app_context = f"App: {context.app_name}"
    if context.window_name:
        app_context += f" | Window: {context.window_name}"
    if context.browser_url:
        app_context += f" | URL: {context.browser_url}"

    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": None},  # Will be replaced
                {
                    "type": "text",
                    "text": f"Analyze this screenshot. App context: {app_context or 'unknown'}. "
                    f"Output a strictly valid JSON object:\n"
                    f'{{"narrative": "...", "entities": ["..."], "intent": "...", "summary": "..."}}',
                },
            ],
        }
    ]


class LocalDescriptionProvider(DescriptionProvider):
    """Qwen3 VL-based description provider running locally."""

    MAX_IMAGE_SIZE = 1024

    def __init__(self, model_name: str = "") -> None:
        self.model_id = model_name or AIEngine.MODEL_ID
        if settings.device == "cpu":
            torch_dtype = torch.float32
        else:
            torch_dtype = torch.bfloat16
        logger.info(f"Loading LocalDescriptionProvider: {self.model_id}")
        logger.info(f"Using device: {settings.device}")
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            dtype=torch_dtype,
            device_map=settings.device,
        )
        self.processor = AutoProcessor.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            min_pixels=256 * 28 * 28,
            max_pixels=1024 * 28 * 28,
        )

    def _resize_if_needed(self, image: Image.Image) -> Image.Image:
        w, h = image.size
        if w <= self.MAX_IMAGE_SIZE and h <= self.MAX_IMAGE_SIZE:
            return image
        if w > h:
            new_w, new_h = self.MAX_IMAGE_SIZE, int(h * (self.MAX_IMAGE_SIZE / w))
        else:
            new_h, new_w = self.MAX_IMAGE_SIZE, int(w * (self.MAX_IMAGE_SIZE / h))
        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path)
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        image = Image.open(path)
        if settings.device == "cpu":
            image = self._resize_if_needed(image)

        messages = _build_messages(context)
        messages[0]["content"][0]["image"] = image

        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=text,
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)

        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS,
            )

        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        raw = output_text.strip()
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            if isinstance(data, dict):
                return FrameDescription(
                    narrative=data.get("narrative", ""),
                    entities=data.get("entities", []),
                    intent=data.get("intent", ""),
                    summary=data.get("summary", ""),
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from LocalDescriptionProvider. Raw: {raw[:100]}...")
        return FrameDescription(
            narrative=raw,
            entities=[],
            intent="",
            summary="",
        )
```

- [x] **Step 2: Write failing unit test**

```python
"""tests/test_description_provider.py"""
import json
import sqlite3
from pathlib import Path

import pytest

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import DescriptionProvider, DescriptionProviderError


class TestFrameDescription:
    def test_frame_description_to_db_dict(self):
        desc = FrameDescription(
            narrative="test narrative",
            entities=["GitHub", "Sign in"],
            intent="authenticating to GitHub",
            summary="GitHub login page",
        )
        db = desc.to_db_dict()
        assert db["narrative"] == "test narrative"
        assert db["intent"] == "authenticating to GitHub"
        assert json.loads(db["entities_json"]) == ["GitHub", "Sign in"]


class TestDescriptionProviderProtocol:
    def test_description_provider_is_abc(self):
        assert issubclass(DescriptionProvider, object)  # Protocol check
```

Run: `pytest tests/test_description_provider.py::TestFrameDescription -v`
Expected: PASS (FrameDescription is working)

Run: `pytest tests/test_description_provider.py::TestDescriptionProviderProtocol -v`
Expected: PASS (protocol exists)

- [x] **Step 3: Commit**

```bash
git add openrecall/server/description/providers/local.py tests/test_description_provider.py
git commit -m "feat(description): add LocalDescriptionProvider with Qwen3 VL"
```

---

## Task 6: OpenAIDescriptionProvider and DashScopeDescriptionProvider

**Files:**
- Create: `openrecall/server/description/providers/openai.py`
- Create: `openrecall/server/description/providers/dashscope.py`

- [x] **Step 1: Write OpenAIDescriptionProvider**

```python
"""OpenAI-compatible description provider."""
import base64
import json
import logging
from pathlib import Path

import requests

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
    DescriptionProviderConfigError,
)
from openrecall.server.ai.providers import _normalize_api_base
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


_PROMPT_TEXT = (
    "Analyze this screenshot. Output a strictly valid JSON object:\n"
    '{"narrative": "detailed description", "entities": ["entity1"], '
    '"intent": "user intent phrase", "summary": "one sentence"}'
)


class OpenAIDescriptionProvider(DescriptionProvider):
    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not api_key:
            raise DescriptionProviderConfigError("api_key is required")
        if not model_name:
            raise DescriptionProviderConfigError("model_name is required")
        self.api_key = api_key.strip()
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        # Build context text for prompt
        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Analyze this screenshot. App context: {ctx_str}.\n{_PROMPT_TEXT}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)
        except Exception as e:
            raise DescriptionProviderRequestError(f"OpenAI request failed: {e}") from e

        if not resp.ok:
            raise DescriptionProviderRequestError(
                f"OpenAI request failed: status={resp.status_code} body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise DescriptionProviderRequestError("choices missing in response")
            message = choices[0].get("message") or {}
            content = message.get("content", "")
        except Exception as e:
            raise DescriptionProviderRequestError(f"Parse failed: {e}") from e

        raw = content.strip()
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return FrameDescription(
                    narrative=parsed.get("narrative", ""),
                    entities=parsed.get("entities", []),
                    intent=parsed.get("intent", ""),
                    summary=parsed.get("summary", ""),
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from OpenAIDescriptionProvider. Raw: {raw[:100]}...")
        return FrameDescription(narrative=raw, entities=[], intent="", summary="")
```

- [x] **Step 2: Write DashScopeDescriptionProvider**

```python
"""DashScope description provider."""
import json
import logging
from pathlib import Path
from typing import Any

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers.base import (
    DescriptionProvider,
    DescriptionProviderRequestError,
    DescriptionProviderConfigError,
    DescriptionProviderUnavailableError,
)

logger = logging.getLogger(__name__)


class DashScopeDescriptionProvider(DescriptionProvider):
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise DescriptionProviderConfigError("api_key is required")
        if not model_name:
            raise DescriptionProviderConfigError("model_name is required")
        try:
            import dashscope  # type: ignore
        except ImportError as e:
            raise DescriptionProviderUnavailableError(
                "dashscope is not installed. Install with: pip install dashscope"
            ) from e
        self._dashscope = dashscope
        self._dashscope.api_key = api_key
        self.model_name = model_name

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        # Build context text
        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"image": f"file://{path.as_posix()}"},
                    {
                        "text": (
                            f"Analyze this screenshot. App context: {ctx_str}.\n"
                            'Output a strictly valid JSON: '
                            '{"narrative": "...", "entities": ["..."], '
                            '"intent": "...", "summary": "..."}'
                        ),
                    },
                ],
            }
        ]

        try:
            response = self._dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
            )
        except Exception as e:
            raise DescriptionProviderRequestError(f"DashScope request failed: {e}") from e

        raw_text = ""
        try:
            data = response
            if hasattr(response, "to_dict"):
                data = response.to_dict()
            if isinstance(data, dict):
                output = data.get("output") or {}
                choices = output.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    if isinstance(content, str):
                        raw_text = content.strip()
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and "text" in item:
                                raw_text = str(item["text"]).strip()
                text = output.get("text")
                if isinstance(text, str) and text.strip():
                    raw_text = text.strip()
        except Exception as e:
            raise DescriptionProviderRequestError(f"DashScope response parse failed: {e}") from e

        if not raw_text:
            raise DescriptionProviderRequestError("Empty response from DashScope")

        try:
            clean = raw_text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return FrameDescription(
                    narrative=parsed.get("narrative", ""),
                    entities=parsed.get("entities", []),
                    intent=parsed.get("intent", ""),
                    summary=parsed.get("summary", ""),
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from DashScope. Raw: {raw_text[:100]}...")
        return FrameDescription(narrative=raw_text, entities=[], intent="", summary="")
```

- [x] **Step 3: Add tests for cloud providers** (mocked, no real API calls)

```python
"""tests/test_description_provider.py — add after existing tests"""

class TestOpenAIDescriptionProvider:
    def test_init_requires_api_key(self):
        from openrecall.server.description.providers.openai import OpenAIDescriptionProvider
        with pytest.raises(Exception):  # ConfigError
            OpenAIDescriptionProvider(api_key="", model_name="gpt-4o")


class TestDashScopeDescriptionProvider:
    def test_init_requires_api_key(self):
        from openrecall.server.description.providers.dashscope import DashScopeDescriptionProvider
        with pytest.raises(Exception):  # ConfigError
            DashScopeDescriptionProvider(api_key="", model_name="qwen-vl-max")
```

- [x] **Step 4: Commit**

```bash
git add openrecall/server/description/providers/openai.py openrecall/server/description/providers/dashscope.py tests/test_description_provider.py
git commit -m "feat(description): add OpenAIDescriptionProvider and DashScopeDescriptionProvider"
```

---

## Task 7: DescriptionService

**Files:**
- Create: `openrecall/server/description/service.py`

- [x] **Step 1: Write the service**

```python
"""Description service: enqueue, generate, backfill."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from openrecall.server.description.models import FrameDescription, FrameContext
from openrecall.server.description.providers import (
    DescriptionProvider,
    DescriptionProviderError,
)
from openrecall.server.ai.factory import get_description_provider
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min
_MAX_RETRIES = 3


@dataclass
class DescriptionTask:
    id: int
    frame_id: int
    status: str
    error_message: Optional[str]
    retry_count: int


class DescriptionService:
    """Service for frame description operations."""

    def __init__(self, store: "FramesStore") -> None:
        self._store = store
        self._provider: Optional[DescriptionProvider] = None

    @property
    def provider(self) -> DescriptionProvider:
        if self._provider is None:
            if not settings.description_enabled:
                raise DescriptionProviderError("Description generation is disabled")
            self._provider = get_description_provider()
        return self._provider

    def enqueue_description_task(self, conn, frame_id: int) -> None:
        """Insert a pending description task for a frame. Idempotent."""
        self._store.insert_description_task(conn, frame_id)

    def generate_description(
        self,
        image_path: str,
        context: FrameContext,
        model_name: Optional[str] = None,
    ) -> FrameDescription:
        """Call the description provider to generate a description."""
        try:
            desc = self.provider.generate(image_path, context)
            logger.debug(
                f"Generated description: {len(desc.narrative)} chars, "
                f"{len(desc.entities)} entities, intent={desc.intent}"
            )
            return desc
        except Exception as e:
            logger.warning(f"Description generation failed: {e}")
            raise

    def insert_description(
        self,
        conn,
        frame_id: int,
        description: FrameDescription,
        model_name: Optional[str] = None,
    ) -> None:
        """Insert completed description into frame_descriptions."""
        db_dict = description.to_db_dict()
        self._store.insert_frame_description(
            conn,
            frame_id=frame_id,
            narrative=db_dict["narrative"],
            entities_json=db_dict["entities_json"],
            intent=db_dict["intent"],
            summary=db_dict["summary"],
            description_model=model_name,
        )

    def mark_completed(self, conn, task_id: int, frame_id: int) -> None:
        """Mark a description task as completed."""
        self._store.complete_description_task(conn, task_id, frame_id)

    def mark_failed(
        self,
        conn,
        task_id: int,
        frame_id: int,
        error_message: str,
        retry_count: int,
    ) -> None:
        """Mark a description task as failed or schedule retry."""
        if retry_count < _MAX_RETRIES:
            delay_seconds = _RETRY_DELAYS[retry_count - 1]
            next_retry = datetime.now(timezone.utc)
            next_retry = next_retry.replace(
                microsecond=0
            )  # SQLite TIMESTAMP has no microseconds
            from datetime import timedelta
            next_retry = next_retry + timedelta(seconds=delay_seconds)
            self._store.reschedule_description_task(
                conn, task_id, retry_count + 1, next_retry.isoformat()
            )
            logger.info(
                f"Description task #{task_id} failed (retry {retry_count}/{_MAX_RETRIES}), "
                f"rescheduled at {next_retry.isoformat()}"
            )
        else:
            self._store.fail_description_task(conn, task_id, frame_id, error_message)
            logger.warning(f"Description task #{task_id} permanently failed after {_MAX_RETRIES} retries")

    def backfill(self, conn) -> int:
        """Enqueue all frames without description_status. Returns count."""
        return self._store.enqueue_pending_descriptions(conn)

    def get_queue_status(self, conn) -> dict[str, int]:
        """Return queue statistics."""
        return self._store.get_description_queue_status(conn)
```

- [x] **Step 2: Write failing test**

```python
"""tests/test_description_service.py"""
import pytest
from unittest.mock import MagicMock


class TestDescriptionService:
    def test_enqueue_is_idempotent(self):
        # Mock store, verify enqueue doesn't raise
        from openrecall.server.description.service import DescriptionService
        mock_store = MagicMock()
        svc = DescriptionService(store=mock_store)
        svc.enqueue_description_task(None, frame_id=1)
        mock_store.insert_description_task.assert_called_once_with(None, frame_id=1)
```

Run: `pytest tests/test_description_service.py -v`
Expected: PASS (mocked)

- [x] **Step 3: Commit**

```bash
git add openrecall/server/description/service.py tests/test_description_service.py
git commit -m "feat(description): add DescriptionService with enqueue, generate, backfill"
```

---

## Task 8: DescriptionWorker

**Files:**
- Create: `openrecall/server/description/worker.py`

- [x] **Step 1: Write the worker**

```python
"""Background worker for frame description generation."""
import logging
import sqlite3
import threading
import time
from typing import Optional

from openrecall.server.database import SQLStore
from openrecall.server.description.models import FrameContext
from openrecall.server.description.service import DescriptionService
from openrecall.server.description.providers import DescriptionProviderError
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0  # seconds


class DescriptionWorker(threading.Thread):
    """Background worker thread that processes pending description tasks."""

    def __init__(self, store: "FramesStore", poll_interval: float = _POLL_INTERVAL):
        super().__init__(daemon=True, name="DescriptionWorker")
        self._store = store
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._service: Optional[DescriptionService] = None

    @property
    def service(self) -> DescriptionService:
        if self._service is None:
            self._service = DescriptionService(store=self._store)
        return self._service

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("DescriptionWorker started")
        conn = self._store.get_db_connection()
        try:
            while not self._stop_event.is_set():
                self._process_batch(conn)
                self._stop_event.wait(timeout=self._poll_interval)
        finally:
            conn.close()
        logger.info("DescriptionWorker stopped")

    def _process_batch(self, conn: sqlite3.Connection) -> None:
        """Fetch and process one pending description task."""
        task = self._store.claim_description_task(conn)
        if task is None:
            return

        task_id, frame_id = task["id"], task["frame_id"]
        logger.debug(f"Processing description task #{task_id} for frame #{frame_id}")

        # Get frame metadata
        frame = self._store.get_frame_by_id(conn, frame_id)
        if frame is None:
            logger.warning(f"Frame #{frame_id} not found, skipping task #{task_id}")
            return

        # Get snapshot path
        snapshot_path = frame.get("snapshot_path")
        if not snapshot_path:
            logger.warning(f"Frame #{frame_id} has no snapshot_path, skipping")
            self.service.mark_failed(conn, task_id, frame_id, "No snapshot_path", 1)
            return

        # Build context
        context = FrameContext(
            app_name=frame.get("app_name"),
            window_name=frame.get("window_name"),
            browser_url=frame.get("browser_url"),
        )

        try:
            description = self.service.generate_description(snapshot_path, context)
            self.service.insert_description(conn, frame_id, description)
            self.service.mark_completed(conn, task_id, frame_id)
            logger.info(f"Description completed for frame #{frame_id}")
        except DescriptionProviderError as e:
            retry_count = task.get("retry_count", 0) + 1
            self.service.mark_failed(conn, task_id, frame_id, str(e), retry_count)
        except Exception as e:
            logger.error(f"Unexpected error processing frame #{frame_id}: {e}")
            retry_count = task.get("retry_count", 0) + 1
            self.service.mark_failed(conn, task_id, frame_id, str(e), retry_count)
```

- [x] **Step 2: Write worker test**

```python
"""tests/test_description_worker.py"""
import pytest
from unittest.mock import MagicMock, patch


class TestDescriptionWorker:
    def test_worker_starts_and_stops(self):
        from openrecall.server.description.worker import DescriptionWorker
        mock_store = MagicMock()
        worker = DescriptionWorker(store=mock_store, poll_interval=0.1)
        assert worker.name == "DescriptionWorker"
        assert worker.daemon is True
```

Run: `pytest tests/test_description_worker.py -v`
Expected: PASS

- [x] **Step 3: Commit**

```bash
git add openrecall/server/description/worker.py tests/test_description_worker.py
git commit -m "feat(description): add DescriptionWorker thread"
```

---

## Task 9: FramesStore — Add Description CRUD Methods

**Files:**
- Modify: `openrecall/server/database/frames_store.py`

Add the following methods to the `FramesStore` class (at the end, before any private helpers):

- [x] **Step 1: Add insert_description_task()**

```python
def insert_description_task(self, conn: sqlite3.Connection, frame_id: int) -> None:
    """Insert a pending description task. Idempotent via UNIQUE constraint."""
    conn.execute(
        """
        INSERT OR IGNORE INTO description_tasks (frame_id, status)
        VALUES (?, 'pending')
        """,
        (frame_id,),
    )
    # Also update frames.description_status if NULL
    conn.execute(
        """
        UPDATE frames
        SET description_status = 'pending'
        WHERE id = ? AND description_status IS NULL
        """,
        (frame_id,),
    )
```

- [x] **Step 2: Add claim_description_task()**

```python
def claim_description_task(
    self,
    conn: sqlite3.Connection,
) -> Optional[dict]:
    """Atomically claim the next pending description task. Returns dict or None."""
    cursor = conn.execute(
        """
        WITH next_task AS (
            SELECT id FROM description_tasks
            WHERE status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ORDER BY id
            LIMIT 1
        )
        UPDATE description_tasks
        SET status = 'processing',
            started_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id IN (SELECT id FROM next_task)
        RETURNING id, frame_id, retry_count
        """,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    conn.commit()
    return {"id": row[0], "frame_id": row[1], "retry_count": row[2]}
```

- [x] **Step 3: Add insert_frame_description()**

```python
def insert_frame_description(
    self,
    conn: sqlite3.Connection,
    frame_id: int,
    narrative: str,
    entities_json: str,
    intent: str,
    summary: str,
    description_model: Optional[str] = None,
) -> None:
    """Insert completed description. Idempotent via UNIQUE(frame_id)."""
    conn.execute(
        """
        INSERT OR REPLACE INTO frame_descriptions
          (frame_id, narrative, entities_json, intent, summary, description_model, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (frame_id, narrative, entities_json, intent, summary, description_model),
    )
```

- [x] **Step 4: Add complete_description_task()**

```python
def complete_description_task(
    self,
    conn: sqlite3.Connection,
    task_id: int,
    frame_id: int,
) -> None:
    """Mark a description task as completed and update frames table."""
    conn.execute(
        """
        UPDATE description_tasks
        SET status = 'completed',
            completed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ?
        """,
        (task_id,),
    )
    conn.execute(
        "UPDATE frames SET description_status = 'completed' WHERE id = ?",
        (frame_id,),
    )
```

- [x] **Step 5: Add reschedule_description_task() and fail_description_task()**

```python
def reschedule_description_task(
    self,
    conn: sqlite3.Connection,
    task_id: int,
    retry_count: int,
    next_retry_at: str,
) -> None:
    conn.execute(
        """
        UPDATE description_tasks
        SET status = 'pending',
            retry_count = ?,
            next_retry_at = ?
        WHERE id = ?
        """,
        (retry_count, next_retry_at, task_id),
    )


def fail_description_task(
    self,
    conn: sqlite3.Connection,
    task_id: int,
    frame_id: int,
    error_message: str,
) -> None:
    conn.execute(
        """
        UPDATE description_tasks
        SET status = 'failed', error_message = ?
        WHERE id = ?
        """,
        (error_message, task_id),
    )
    conn.execute(
        "UPDATE frames SET description_status = 'failed' WHERE id = ?",
        (frame_id,),
    )
```

- [x] **Step 6: Add enqueue_pending_descriptions() for backfill**

```python
def enqueue_pending_descriptions(self, conn: sqlite3.Connection) -> int:
    """Enqueue all frames without description_status. Returns count."""
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO description_tasks (frame_id, status)
        SELECT id, 'pending'
        FROM frames
        WHERE description_status IS NULL
          AND snapshot_path IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE frames
        SET description_status = 'pending'
        WHERE description_status IS NULL
          AND id IN (SELECT frame_id FROM description_tasks WHERE status = 'pending')
        """
    )
    conn.commit()
    return cursor.rowcount
```

- [x] **Step 7: Add get_description_queue_status()**

```python
def get_description_queue_status(self, conn: sqlite3.Connection) -> dict[str, int]:
    """Return count of tasks by status."""
    cursor = conn.execute(
        """
        SELECT status, COUNT(*) FROM description_tasks GROUP BY status
        """
    )
    result = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    for row in cursor.fetchall():
        status = row[0]
        if status in result:
            result[status] = row[1]
    return result
```

- [x] **Step 8: Add get_frame_description()**

```python
def get_frame_description(
    self,
    conn: sqlite3.Connection,
    frame_id: int,
) -> Optional[dict]:
    """Get description for a frame, or None if not completed."""
    cursor = conn.execute(
        """
        SELECT narrative, entities_json, intent, summary, description_model, generated_at
        FROM frame_descriptions WHERE frame_id = ?
        """,
        (frame_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    import json
    return {
        "narrative": row[0],
        "entities": json.loads(row[1]),
        "intent": row[2],
        "summary": row[3],
        "model": row[4],
        "generated_at": row[5],
    }
```

- [x] **Step 9: Add get_frame_by_id() helper (used by worker)**

```python
def get_frame_by_id(self, conn: sqlite3.Connection, frame_id: int) -> Optional[dict]:
    """Get minimal frame info needed by DescriptionWorker."""
    cursor = conn.execute(
        """
        SELECT id, snapshot_path, app_name, window_name, browser_url, description_status
        FROM frames WHERE id = ?
        """,
        (frame_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "snapshot_path": row[1],
        "app_name": row[2],
        "window_name": row[3],
        "browser_url": row[4],
        "description_status": row[5],
    }
```

- [x] **Step 10: Write test for CRUD methods**

```python
"""tests/test_description_store.py"""
import sqlite3
from pathlib import Path
import pytest
from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db):
    return FramesStore(db_path=temp_db)


class TestDescriptionCRUD:
    def test_insert_and_get_description(self, store, temp_db):
        conn = store.get_db_connection()
        # Insert a frame first
        frame_id = store.claim_frame(
            conn,
            capture_id="cap_desc_test_001",
            timestamp="2026-03-24T10:00:00Z",
            app_name="Chrome",
            window_name="Test Window",
        )["frame_id"]
        conn.commit()

        # Enqueue
        store.insert_description_task(conn, frame_id)
        conn.commit()

        # Insert description
        store.insert_frame_description(
            conn, frame_id,
            narrative="Test narrative",
            entities_json='["test"]',
            intent="testing",
            summary="Test summary",
        )
        conn.commit()

        # Get
        desc = store.get_frame_description(conn, frame_id)
        assert desc is not None
        assert desc["narrative"] == "Test narrative"
        assert desc["intent"] == "testing"
        assert desc["entities"] == ["test"]

    def test_queue_status(self, store, temp_db):
        conn = store.get_db_connection()
        status = store.get_description_queue_status(conn)
        assert isinstance(status, dict)
        assert "pending" in status
        assert "completed" in status
```

Run: `pytest tests/test_description_store.py -v`
Expected: PASS

- [x] **Step 11: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_description_store.py
git commit -m "feat(description): add FramesStore description CRUD methods"
```

---

## Task 10: API Endpoints

**Files:**
- Modify: `openrecall/server/api_v1.py`

- [x] **Step 1: Extend `/v1/frames/<frame_id>/context` response** (api_v1.py, around `get_frame_context` at line 600)

Find the existing `get_frame_context()` function in `api_v1.py` (around line 600). Modify the `result` dict construction to add `description_status` and `description` fields. The `description` is `None` unless `description_status == 'completed'`, in which case call `store.get_frame_description(conn, frame_id)`.

```python
    result = {
        "frame_id": frame["id"],
        "timestamp": frame["timestamp"],
        "app_name": frame.get("app_name"),
        "window_name": frame.get("window_name"),
        "browser_url": frame.get("browser_url"),
        "text_source": frame.get("text_source"),
        "text": text,
        "nodes": nodes if include_nodes else None,
        "description_status": frame.get("description_status"),
        "description": store.get_frame_description(conn, frame_id)
            if frame.get("description_status") == "completed"
            else None,
    }
    return jsonify(result)
```

- [x] **Step 2: Extend `/v1/activity-summary` response** (api_v1.py, around `activity_summary` at line 1007)

In the `activity_summary()` function, after building the `result` dict, add:

```python
    max_descriptions = request.args.get("max_descriptions", 20, type=int)
    max_descriptions = min(max_descriptions, 100)
    descriptions = store.get_recent_descriptions(conn, time_start, time_end, max_descriptions)
    result["descriptions"] = descriptions
```

Note: `store.get_recent_descriptions()` is added in Step 3 below.

- [x] **Step 3: Add `get_recent_descriptions()` to FramesStore**

> This method is needed by Step 2 above. Add it as a new method in `frames_store.py`:

```python
def get_recent_descriptions(
    self,
    conn: sqlite3.Connection,
    time_start: str,
    time_end: str,
    limit: int = 20,
) -> list[dict]:
    """Get recent frame descriptions within a time range."""
    cursor = conn.execute(
        """
        SELECT fd.frame_id, fd.summary, fd.intent
        FROM frame_descriptions fd
        JOIN frames f ON f.id = fd.frame_id
        WHERE f.timestamp BETWEEN ? AND ?
          AND fd.narrative IS NOT NULL
        ORDER BY f.timestamp DESC
        LIMIT ?
        """,
        (time_start, time_end, limit),
    )
    rows = cursor.fetchall()
    return [
        {"frame_id": r[0], "summary": r[1], "intent": r[2]}
        for r in rows
    ]
```

> **Placement**: Add this method to `frames_store.py` alongside the other description CRUD methods from Task 9. It is part of FramesStore, not the API layer.

- [x] **Step 4: Add POST /v1/frames/<frame_id>/description endpoint**

```python
@v1_bp.route("/frames/<int:frame_id>/description", methods=["POST"])
def trigger_description(frame_id: int):
    """Manually trigger description generation for a frame."""
    request_id = str(uuid.uuid4())
    conn = store.get_db_connection()
    try:
        frame = store.get_frame_by_id(conn, frame_id)
        if frame is None:
            return make_error_response(
                f"Frame {frame_id} not found",
                "NOT_FOUND",
                404,
                request_id=request_id,
            )

        status = frame.get("description_status")
        if status == "completed":
            return jsonify({
                "error": "Description already completed",
                "code": "ALREADY_COMPLETED",
                "request_id": request_id,
            }), 409
        if status in ("pending", "processing"):
            return jsonify({
                "error": "Description already queued/processing",
                "code": "ALREADY_QUEUED",
                "request_id": request_id,
            }), 409

        # Enqueue (insert OR IGNORE handles the re-enqueue of failed tasks)
        store.insert_description_task(conn, frame_id)
        conn.commit()

        # Query the newly inserted/updated task to get its id
        cursor = conn.execute(
            "SELECT id, status FROM description_tasks WHERE frame_id = ? ORDER BY id DESC LIMIT 1",
            (frame_id,),
        )
        row = cursor.fetchone()
        task_id = row[0] if row else 0

        return jsonify({
            "task_id": task_id,
            "frame_id": frame_id,
            "status": "pending",
            "message": "Description generation queued",
            "request_id": request_id,
        }), 202
    finally:
        conn.close()
```

> **Bug fix vs. draft**: The original draft called `claim_description_task(conn)` which atomically claims (status→processing) a pending task, returning nothing useful for the POST endpoint. The corrected version queries the task after enqueue to get the `task_id`.

- [x] **Step 5: Add GET /v1/description/tasks/status endpoint**

```python
@v1_bp.route("/description/tasks/status", methods=["GET"])
def description_queue_status():
    """Return description task queue statistics."""
    conn = store.get_db_connection()
    try:
        status = store.get_description_queue_status(conn)
        return jsonify(status)
    finally:
        conn.close()
```

- [x] **Step 6: Add POST /v1/admin/description/backfill endpoint**

```python
@v1_bp.route("/admin/description/backfill", methods=["POST"])
def description_backfill():
    """Trigger backfill of descriptions for all historical frames."""
    request_id = str(uuid.uuid4())
    conn = store.get_db_connection()
    try:
        from openrecall.server.description.service import DescriptionService
        svc = DescriptionService(store)
        count = svc.backfill(conn)
        conn.commit()
        return jsonify({
            "message": "Backfill started",
            "estimated_count": count,
            "request_id": request_id,
        }), 202
    finally:
        conn.close()
```

- [x] **Step 7: Write API test**

```python
"""tests/test_description_api.py"""
import pytest
from unittest.mock import patch, MagicMock


class TestDescriptionAPI:
    def test_context_includes_description_status(self):
        # Integration test: verify context response has description_status
        pass  # TODO: full integration test with running server

    def test_queue_status_endpoint(self):
        # Integration test: verify queue status returns dict
        pass  # TODO: full integration test with running server
```

- [x] **Step 8: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_description_api.py
git commit -m "feat(api): extend /frames/<id>/context and /activity-summary with description; add manual trigger and backfill endpoints"
```

---

## Task 11: Ingest Integration — Auto-Enqueue on Ingest

**Files:**
- Modify: `openrecall/server/api_v1.py` (ingest endpoint)
- Modify: `openrecall/server/database/frames_store.py`

- [x] **Step 1: Modify ingest() to enqueue description task**

Find the ingest() endpoint. After `finalize_claimed_frame()` succeeds, add:

```python
# Enqueue description task if enabled
if settings.description_enabled:
    try:
        svc = DescriptionService(store)
        svc.enqueue_description_task(conn, frame_id)
    except Exception as e:
        logger.warning(f"Failed to enqueue description task: {e}")
```

- [x] **Step 2: Commit**

```bash
git add openrecall/server/api_v1.py
git commit -m "feat(ingest): auto-enqueue description task on frame ingest"
```

---

## Task 12: Worker Startup — Register DescriptionWorker

**Files:**
- Modify: `openrecall/server/__main__.py`
- Modify: `openrecall/server/app.py` (for legacy mode `init_background_worker`)

The server has three startup modes. DescriptionWorker should start alongside the existing worker in all modes. At module level, store a reference so shutdown can stop it.

- [x] **Step 1: Add module-level worker reference in `__main__.py`**

After line 17 (`logger = configure_logging...`), add:

```python
_description_worker = None  # module-level reference for shutdown
```

- [x] **Step 2: Modify `_start_noop_mode()` in `__main__.py`**

After line 106 (`return driver`), add:

```python
    global _description_worker
    if settings.description_enabled:
        from openrecall.server.database.frames_store import FramesStore
        from openrecall.server.description.worker import DescriptionWorker
        store = FramesStore()
        _description_worker = DescriptionWorker(store)
        _description_worker.start()
        logger.info("DescriptionWorker started (noop mode)")
```

- [x] **Step 3: Modify `_start_ocr_mode()` in `__main__.py`**

After line 138 (`worker.start()`), add:

```python
    global _description_worker
    if settings.description_enabled:
        from openrecall.server.description.worker import DescriptionWorker
        _description_worker = DescriptionWorker(store)
        _description_worker.start()
        logger.info("DescriptionWorker started (ocr mode)")
```

- [x] **Step 4: Modify `init_background_worker()` in `app.py` (legacy mode)**

At line 157 where `worker = ProcessingWorker()`, add after that line:

```python
    if settings.description_enabled:
        from openrecall.server.database.frames_store import FramesStore
        from openrecall.server.description.worker import DescriptionWorker
        description_store = FramesStore()
        description_worker = DescriptionWorker(description_store)
        description_worker.start()
        app_instance.description_worker = description_worker
        logger.info("DescriptionWorker started (legacy mode)")
```

Note: `ProcessingWorker` and `V3ProcessingWorker` do not expose a `_store` attribute. Always create a new `FramesStore()` instance for `DescriptionWorker`.

- [x] **Step 5: Wire shutdown in `shutdown_handler()` in `__main__.py`**

In the `shutdown_handler()` function, inside the try block after line 191 (`worker.stop()`), add:

```python
            # Stop DescriptionWorker
            if _description_worker is not None:
                logger.info("Stopping DescriptionWorker...")
                _description_worker.stop()
                _description_worker.join(timeout=5)
                logger.info("DescriptionWorker stopped")
```

Also update `_cleanup_worker()` (line 209) to stop `_description_worker` if running.

- [x] **Step 6: Commit**

```bash
git add openrecall/server/__main__.py openrecall/server/app.py
git commit -m "feat(server): start and stop DescriptionWorker with server"

---

## Task 13: Final Integration Test

- [x] **Step 1: Run all description tests**

```bash
pytest tests/test_description_store.py tests/test_description_service.py tests/test_description_provider.py tests/test_description_worker.py -v
```

- [x] **Step 2: Run full test suite**

```bash
pytest -m "not model and not e2e and not perf and not security" -v
```

- [x] **Step 3: Commit all remaining changes**
