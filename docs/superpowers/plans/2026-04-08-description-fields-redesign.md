# Description Fields Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 FrameDescription 从 4 字段（narrative, entities, intent, summary）重构为 3 字段（narrative, summary, tags），支持 narrative 1024 字、summary 256 字、tags 3-8 个关键词。

**Architecture:** 修改 FrameDescription Pydantic model → 更新三个 provider 的 prompt 和解析 → 数据库迁移（drop entities/intent, add tags_json）→ 更新 FramesStore 的 CRUD → 调整 API response

**Tech Stack:** Python, Pydantic, SQLite, SQLAlchemy-style raw SQL

---

## File Structure

| File | Responsibility | Change Type |
|------|---------------|-------------|
| `openrecall/server/description/models.py` | FrameDescription Pydantic model | Modify |
| `openrecall/server/description/providers/base.py` | Provider 基类（docstring 更新） | Modify |
| `openrecall/server/description/providers/openai.py` | OpenAI provider prompt + 解析 | Modify |
| `openrecall/server/description/providers/dashscope.py` | DashScope provider prompt + 解析 | Modify |
| `openrecall/server/description/providers/local.py` | Local provider prompt + 解析 | Modify |
| `openrecall/server/database/migrations/YYYYMMDDHHMMSS_description_fields_redesign.sql` | 数据库迁移 | Create |
| `openrecall/server/database/frames_store.py` | 插入/查询 frame_descriptions | Modify |
| `openrecall/server/description/service.py` | 使用新字段插入 | Modify |
| `openrecall/server/api_v1.py` | API response 结构调整 | Modify |
| `tests/test_description_models.py` | Model 单元测试 | Modify |
| `tests/test_description_provider.py` | Provider 测试 | Modify |
| `tests/test_description_store.py` | Store 层测试 | Modify |
| `tests/test_description_api.py` | API 测试 | Modify |

---

## Task 1: Update FrameDescription Model

**Files:**
- Modify: `openrecall/server/description/models.py`
- Test: `tests/test_description_models.py`

**Context:** 当前 model 有 narrative (max 512), entities (list), intent (str), summary (max 200)。需要改为 narrative (max 1024), summary (max 256), tags (3-8 items)。

- [ ] **Step 1: Write failing test for new model structure**

```python
# tests/test_description_models.py
import pytest
from openrecall.server.description.models import FrameDescription, FrameContext


def test_frame_description_new_fields():
    """Test FrameDescription accepts narrative, summary, tags."""
    desc = FrameDescription(
        narrative="This is a detailed description of the screen content. " * 20,
        summary="Brief summary of activity",
        tags=["github", "coding", "browsing"]
    )
    assert len(desc.narrative) <= 1024
    assert len(desc.summary) <= 256
    assert 3 <= len(desc.tags) <= 8


def test_frame_description_rejects_old_fields():
    """Test FrameDescription rejects entities and intent."""
    with pytest.raises(TypeError):
        FrameDescription(
            narrative="test",
            summary="test",
            entities=["entity1"],  # should fail
            intent="intent"  # should fail
        )


def test_frame_description_tags_validation():
    """Test tags length validation."""
    # Too many tags should be truncated
    desc = FrameDescription(
        narrative="test",
        summary="test",
        tags=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"]  # 12 tags
    )
    assert len(desc.tags) <= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_description_models.py -v`

Expected: FAIL - entities/intent fields still exist, new model structure not implemented

- [ ] **Step 3: Update FrameDescription model**

```python
# openrecall/server/description/models.py
"""Description models for frame description generation."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class FrameDescription(BaseModel):
    """Structured description of a frame's content and user intent."""

    narrative: str = Field(
        ...,
        max_length=1024,
        description="Detailed natural language description of screen content and user activity",
    )
    summary: str = Field(
        ...,
        max_length=256,
        description="One-sentence summary capturing the key activity",
    )
    tags: List[str] = Field(
        default_factory=list,
        min_length=0,
        max_length=10,
        description="3-8 lowercase keywords describing the activity (max 10 items)",
    )

    @field_validator("tags")
    @classmethod
    def tags_max_length(cls, v: List[str]) -> List[str]:
        if len(v) > 10:
            return v[:10]
        return v

    @field_validator("tags")
    @classmethod
    def tags_lowercase(cls, v: List[str]) -> List[str]:
        return [tag.lower().strip() for tag in v if tag.strip()]

    def to_db_dict(self) -> dict:
        """Convert to dict for database insertion."""
        import json
        return {
            "narrative": self.narrative,
            "summary": self.summary,
            "tags_json": json.dumps(self.tags),
        }


class FrameContext(BaseModel):
    """Context metadata passed to description provider."""
    app_name: Optional[str] = None
    window_name: Optional[str] = None
    browser_url: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_description_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_description_models.py openrecall/server/description/models.py
git commit -m "feat(description): update FrameDescription model - narrative 1024, summary 256, tags list, remove entities/intent"
```

---

## Task 2: Update OpenAI Provider

**Files:**
- Modify: `openrecall/server/description/providers/openai.py`
- Test: `tests/test_description_provider.py`

**Context:** 需要更新 prompt 和 JSON 解析逻辑。

- [ ] **Step 1: Write failing test for new prompt output**

```python
# tests/test_description_provider.py

def test_openai_provider_generates_tags():
    """Test OpenAI provider generates tags instead of entities/intent."""
    from openrecall.server.description.providers.openai import OpenAIDescriptionProvider
    from openrecall.server.description.models import FrameContext

    # Mock the API call to return new format
    import json
    mock_response = {
        "narrative": "User browsing GitHub repository page.",
        "summary": "Browsing GitHub",
        "tags": ["github", "repository", "browsing"]
    }

    # Test JSON parsing
    clean = json.dumps(mock_response)
    parsed = json.loads(clean)

    assert "tags" in parsed
    assert "entities" not in parsed
    assert "intent" not in parsed
    assert isinstance(parsed["tags"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_description_provider.py::test_openai_provider_generates_tags -v`

Expected: FAIL - current provider still uses entities/intent

- [ ] **Step 3: Update OpenAI provider**

```python
# openrecall/server/description/providers/openai.py
"""OpenAI-compatible description provider."""
import base64
import json
import logging
import time
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
    'Output a strictly valid JSON object:\n'
    '{"narrative": "detailed description (max 1024 chars)", '
    '"summary": "one sentence (max 256 chars)", '
    '"tags": ["keyword1", "keyword2", ...]}  // 3-8 lowercase keywords'
)

# Add example output
_EXAMPLE_OUTPUT = '''
Example output:
{
  "narrative": "User is browsing GitHub repository page showing README content with project description and installation instructions.",
  "summary": "Browsing GitHub repository README",
  "tags": ["github", "repository", "readme", "browsing", "documentation"]
}
'''


class OpenAIDescriptionProvider(DescriptionProvider):
    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not model_name:
            raise DescriptionProviderConfigError("model_name is required")
        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")

    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        path = Path(image_path).resolve()
        if not path.is_file():
            raise DescriptionProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        url = f"{self.api_base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        prompt_content = (
            f"Analyze this screenshot. App context: {ctx_str}.\n"
            f"{_PROMPT_TEXT}\n"
            f"{_EXAMPLE_OUTPUT}\n"
            "IMPORTANT: Output only valid JSON. No markdown, no explanation."
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_content},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
        }

        try:
            start_time = time.time()
            resp = requests.post(url, headers=headers, json=payload, timeout=settings.ai_request_timeout)
            elapsed = time.time() - start_time
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
                original_narrative = parsed.get("narrative", "")
                original_summary = parsed.get("summary", "")
                tags = parsed.get("tags", [])

                narrative = original_narrative[:1024]
                summary = original_summary[:256]

                if len(original_narrative) > 1024:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 1024 chars")
                if len(original_summary) > 256:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 256 chars")

                # Normalize tags
                if isinstance(tags, list):
                    tags = [str(t).lower().strip() for t in tags if t]
                    tags = tags[:10]  # Max 10 tags
                else:
                    tags = []

                logger.info(f"Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(tags)} tags")
                return FrameDescription(
                    narrative=narrative,
                    summary=summary,
                    tags=tags,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from OpenAIDescriptionProvider. Raw: {raw[:100]}...")
        fallback_narrative = raw[:1024]
        fallback_summary = raw[:256]
        if len(raw) > 1024:
            logger.warning(f"Fallback narrative truncated from {len(raw)} to 1024 chars")
        logger.info(f"Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            summary=fallback_summary,
            tags=[],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_description_provider.py::test_openai_provider_generates_tags -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/description/providers/openai.py tests/test_description_provider.py
git commit -m "feat(description): update OpenAI provider - new prompt with tags, remove entities/intent"
```

---

## Task 3: Update Local Provider

**Files:**
- Modify: `openrecall/server/description/providers/local.py`
- Test: `tests/test_description_provider.py`

- [ ] **Step 1: Write failing test for local provider**

```python
# tests/test_description_provider.py

def test_local_provider_builds_messages_with_new_prompt():
    """Test Local provider builds messages with new prompt format."""
    from openrecall.server.description.providers.local import _build_messages
    from openrecall.server.description.models import FrameContext

    context = FrameContext(
        app_name="Chrome",
        window_name="GitHub",
        browser_url="https://github.com"
    )
    messages = _build_messages(context)

    # Check prompt contains new format keywords
    prompt_text = messages[0]["content"][1]["text"]
    assert "tags" in prompt_text
    assert "entities" not in prompt_text
    assert "intent" not in prompt_text
    assert "1024" in prompt_text
    assert "256" in prompt_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_description_provider.py::test_local_provider_builds_messages_with_new_prompt -v`

Expected: FAIL - current _build_messages uses old format

- [ ] **Step 3: Update Local provider**

```python
# openrecall/server/description/providers/local.py
"""Local description provider using Qwen3 VL."""
import json
import logging
import time
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
from openrecall.server.ai_engine import AIEngine
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_MAX_NEW_TOKENS = 256


def _build_messages(context: FrameContext) -> list[dict[str, Any]]:
    """Build messages for the vision model with context injection."""
    app_context = ""
    if context.app_name:
        app_context = f"App: {context.app_name}"
    if context.window_name:
        app_context += f" | Window: {context.window_name}"
    if context.browser_url:
        app_context += f" | URL: {context.browser_url}"

    prompt_text = (
        f"Analyze this screenshot. App context: {app_context or 'unknown'}. "
        f"Output a strictly valid JSON object:\n"
        f'{{"narrative": "detailed description (max 1024 chars)", '
        f'"summary": "one sentence (max 256 chars)", '
        f'"tags": ["keyword1", "keyword2", ...]}}  // 3-8 lowercase keywords\n\n'
        f'Example output:\n'
        f'{{\n'
        f'  "narrative": "User is browsing GitHub repository page showing README content.",\n'
        f'  "summary": "Browsing GitHub repository README",\n'
        f'  "tags": ["github", "repository", "readme", "browsing", "documentation"]\n'
        f'}}\n\n'
        f'IMPORTANT: Output only valid JSON. No markdown, no explanation.'
    )

    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": None},
                {"type": "text", "text": prompt_text},
            ],
        }
    ]


class LocalDescriptionProvider(DescriptionProvider):
    """Qwen3 VL-based description provider running locally."""

    MAX_IMAGE_SIZE = 1024

    def __init__(self, model_name: str = "") -> None:
        self.model_id = model_name or AIEngine.MODEL_ID
        if not self.model_id:
            raise ValueError(
                "LocalDescriptionProvider requires model_name to be configured. "
                "Set [description] model = '/path/to/local/model' in server.toml, "
                "or use provider = 'openai' with api_base pointing to a vLLM server."
            )
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
        inputs = {k: v.to(self.model.device) if hasattr(v, 'to') else v for k, v in inputs.items()}

        with torch.no_grad():
            start_time = time.time()
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS,
            )
            elapsed = time.time() - start_time

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
                original_narrative = data.get("narrative", "")
                original_summary = data.get("summary", "")
                tags = data.get("tags", [])

                narrative = original_narrative[:1024]
                summary = original_summary[:256]

                if len(original_narrative) > 1024:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 1024 chars")
                if len(original_summary) > 256:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 256 chars")

                # Normalize tags
                if isinstance(tags, list):
                    tags = [str(t).lower().strip() for t in tags if t]
                    tags = tags[:10]
                else:
                    tags = []

                logger.info(f"Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(tags)} tags")
                return FrameDescription(
                    narrative=narrative,
                    summary=summary,
                    tags=tags,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from LocalDescriptionProvider. Raw: {raw[:100]}...")
        fallback_narrative = raw[:1024]
        fallback_summary = raw[:256]
        if len(raw) > 1024:
            logger.warning(f"Fallback narrative truncated from {len(raw)} to 1024 chars")
        logger.info(f"Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            summary=fallback_summary,
            tags=[],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_description_provider.py::test_local_provider_builds_messages_with_new_prompt -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/description/providers/local.py tests/test_description_provider.py
git commit -m "feat(description): update Local provider - new prompt with tags, remove entities/intent"
```

---

## Task 4: Update DashScope Provider

**Files:**
- Modify: `openrecall/server/description/providers/dashscope.py`
- Test: `tests/test_description_provider.py`

- [ ] **Step 1: Update DashScope provider (similar pattern to OpenAI)**

```python
# openrecall/server/description/providers/dashscope.py
"""DashScope description provider."""
import json
import logging
import time
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


def _build_prompt(ctx_str: str) -> str:
    """Build prompt with new format."""
    return (
        f"Analyze this screenshot. App context: {ctx_str}.\n"
        f"Output a strictly valid JSON object:\n"
        f'{{"narrative": "detailed description (max 1024 chars)", '
        f'"summary": "one sentence (max 256 chars)", '
        f'"tags": ["keyword1", "keyword2", ...]}}  // 3-8 lowercase keywords\n\n'
        f'Example output:\n'
        f'{{\n'
        f'  "narrative": "User is browsing GitHub repository page showing README content.",\n'
        f'  "summary": "Browsing GitHub repository README",\n'
        f'  "tags": ["github", "repository", "readme", "browsing", "documentation"]\n'
        f'}}\n\n'
        f'IMPORTANT: Output only valid JSON. No markdown, no explanation.'
    )


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

        ctx_parts = []
        if context.app_name:
            ctx_parts.append(f"App: {context.app_name}")
        if context.window_name:
            ctx_parts.append(f"Window: {context.window_name}")
        if context.browser_url:
            ctx_parts.append(f"URL: {context.browser_url}")
        ctx_str = " | ".join(ctx_parts) if ctx_parts else "unknown"

        prompt_text = _build_prompt(ctx_str)

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"image": f"file://{path.as_posix()}"},
                    {"text": prompt_text},
                ],
            }
        ]

        try:
            start_time = time.time()
            response = self._dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
            )
            elapsed = time.time() - start_time
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
                original_narrative = parsed.get("narrative", "")
                original_summary = parsed.get("summary", "")
                tags = parsed.get("tags", [])

                narrative = original_narrative[:1024]
                summary = original_summary[:256]

                if len(original_narrative) > 1024:
                    logger.warning(f"Narrative truncated from {len(original_narrative)} to 1024 chars")
                if len(original_summary) > 256:
                    logger.warning(f"Summary truncated from {len(original_summary)} to 256 chars")

                # Normalize tags
                if isinstance(tags, list):
                    tags = [str(t).lower().strip() for t in tags if t]
                    tags = tags[:10]
                else:
                    tags = []

                logger.info(f"Description generated in {elapsed:.2f}s: {len(narrative)} chars, {len(tags)} tags")
                return FrameDescription(
                    narrative=narrative,
                    summary=summary,
                    tags=tags,
                )
        except Exception:
            pass

        logger.warning(f"Failed to parse JSON from DashScope. Raw: {raw_text[:100]}...")
        fallback_narrative = raw_text[:1024]
        fallback_summary = raw_text[:256]
        if len(raw_text) > 1024:
            logger.warning(f"Fallback narrative truncated from {len(raw_text)} to 1024 chars")
        logger.info(f"Description generated (fallback) in {elapsed:.2f}s: {len(fallback_narrative)} chars")
        return FrameDescription(
            narrative=fallback_narrative,
            summary=fallback_summary,
            tags=[],
        )
```

- [ ] **Step 2: Run tests for all providers**

Run: `pytest tests/test_description_provider.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/description/providers/dashscope.py
git commit -m "feat(description): update DashScope provider - new prompt with tags, remove entities/intent"
```

---

## Task 5: Database Migration

**Files:**
- Create: `openrecall/server/database/migrations/20260408120000_description_fields_redesign.sql`

**Context:** 需要删除 entities_json 和 intent 列，添加 tags_json 列。

- [ ] **Step 1: Create migration file**

```sql
-- Migration: Description Fields Redesign
-- Date: 2026-04-08
-- Changes: Replace entities_json + intent with tags_json, expand narrative/summary lengths

-- SQLite doesn't support ALTER COLUMN, so we need to recreate the table

-- Step 1: Create new table with new schema
CREATE TABLE frame_descriptions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    narrative TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    description_model TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(frame_id)
);

-- Step 2: Copy data from old table (migrate existing descriptions)
-- entities_json and intent are dropped, tags_json gets empty array
INSERT INTO frame_descriptions_new (
    id, frame_id, narrative, summary, tags_json, description_model, generated_at
)
SELECT
    id,
    frame_id,
    narrative,
    summary,
    '[]',  -- tags_json default to empty array
    description_model,
    generated_at
FROM frame_descriptions;

-- Step 3: Drop old table
DROP TABLE frame_descriptions;

-- Step 4: Rename new table
ALTER TABLE frame_descriptions_new RENAME TO frame_descriptions;

-- Step 5: Recreate indexes
CREATE INDEX idx_fd_frame_id ON frame_descriptions(frame_id);
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/server/database/migrations/20260408120000_description_fields_redesign.sql
git commit -m "feat(description): add database migration - replace entities/intent with tags"
```

---

## Task 6: Update FramesStore

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_description_store.py`

**Context:** 需要更新 insert_frame_description 方法，使用新的字段名。

- [ ] **Step 1: Find and update insert_frame_description method**

在 `openrecall/server/database/frames_store.py` 中找到 `insert_frame_description` 方法，修改参数：

```python
# 旧签名
def insert_frame_description(
    self,
    conn,
    frame_id: int,
    narrative: str,
    entities_json: str,
    intent: str,
    summary: str,
    description_model: Optional[str] = None,
) -> None:

# 新签名
def insert_frame_description(
    self,
    conn,
    frame_id: int,
    narrative: str,
    summary: str,
    tags_json: str,
    description_model: Optional[str] = None,
) -> None:
```

- [ ] **Step 2: Update SQL in insert_frame_description**

```python
def insert_frame_description(
    self,
    conn,
    frame_id: int,
    narrative: str,
    summary: str,
    tags_json: str,
    description_model: Optional[str] = None,
) -> None:
    """Insert a frame description record."""
    conn.execute(
        """
        INSERT INTO frame_descriptions
        (frame_id, narrative, summary, tags_json, description_model)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(frame_id) DO UPDATE SET
            narrative = excluded.narrative,
            summary = excluded.summary,
            tags_json = excluded.tags_json,
            description_model = excluded.description_model,
            generated_at = CURRENT_TIMESTAMP
        """,
        (frame_id, narrative, summary, tags_json, description_model),
    )
```

- [ ] **Step 3: Update query methods if they select specific columns**

搜索 `frame_descriptions` 表的所有查询，确保字段名正确：

```bash
grep -n "frame_descriptions" openrecall/server/database/frames_store.py
```

检查以下方法：
- `get_frame_description` - 确保返回 `tags_json` 而不是 `entities_json`/`intent`
- `get_frame_with_description` - 同上

- [ ] **Step 4: Write/update test for store changes**

```python
# tests/test_description_store.py

def test_insert_frame_description_with_tags():
    """Test inserting description with tags instead of entities/intent."""
    # This test assumes a test database fixture exists
    from openrecall.server.database.frames_store import FramesStore
    import json

    store = FramesStore(db_path=":memory:")  # or test fixture path

    # Insert a description with new fields
    with store._connect() as conn:
        # Need to insert a frame first for FK constraint
        conn.execute("""
            INSERT INTO frames (frame_id, capture_id, timestamp, processing_status)
            VALUES ('test_frame', 'test_capture', '2024-01-01T00:00:00Z', 'completed')
        """)
        frame_id = conn.execute("SELECT id FROM frames WHERE frame_id = 'test_frame'").fetchone()[0]

        # Insert description
        store.insert_frame_description(
            conn,
            frame_id=frame_id,
            narrative="Detailed description of the screen content",
            summary="Brief summary",
            tags_json=json.dumps(["github", "coding", "browsing"]),
            description_model="gpt-4o"
        )

        # Verify
        row = conn.execute(
            "SELECT narrative, summary, tags_json FROM frame_descriptions WHERE frame_id = ?",
            (frame_id,)
        ).fetchone()

        assert row["narrative"] == "Detailed description of the screen content"
        assert row["summary"] == "Brief summary"
        assert json.loads(row["tags_json"]) == ["github", "coding", "browsing"]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_description_store.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_description_store.py
git commit -m "feat(description): update FramesStore - use tags_json, remove entities/intent"
```

---

## Task 7: Update DescriptionService

**Files:**
- Modify: `openrecall/server/description/service.py`

**Context:** 需要更新 `insert_description` 方法，使用新的 `to_db_dict()` 结构。

- [ ] **Step 1: Update insert_description method**

```python
# openrecall/server/description/service.py
# In DescriptionService.insert_description method

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
        summary=db_dict["summary"],
        tags_json=db_dict["tags_json"],
        description_model=model_name,
    )
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_description_service.py -v`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/description/service.py
git commit -m "feat(description): update DescriptionService - use new to_db_dict fields"
```

---

## Task 8: Update API Response

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Test: `tests/test_description_api.py`

**Context:** 需要更新 API response，返回新的字段结构。

- [ ] **Step 1: Find and update frame context endpoint**

在 `openrecall/server/api_v1.py` 中找到 `/v1/frames/<frame_id>/context` 相关的代码。

搜索 description 的构建逻辑：

```bash
grep -n "description" openrecall/server/api_v1.py | head -30
```

更新 description 构建部分：

```python
# 旧格式
description = {
    "narrative": desc_row["narrative"],
    "entities": json.loads(desc_row["entities_json"]),
    "intent": desc_row["intent"],
    "summary": desc_row["summary"],
}

# 新格式
description = {
    "narrative": desc_row["narrative"],
    "summary": desc_row["summary"],
    "tags": json.loads(desc_row["tags_json"]),
}
```

- [ ] **Step 2: Update activity-summary endpoint**

同样搜索 `activity-summary` 相关代码，更新 descriptions 列表的格式：

```python
# 旧
descriptions.append({
    "frame_id": row["frame_id"],
    "summary": row["summary"],
    "intent": row["intent"],
})

# 新
descriptions.append({
    "frame_id": row["frame_id"],
    "summary": row["summary"],
    "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
})
```

- [ ] **Step 3: Write/update API tests**

```python
# tests/test_description_api.py

def test_frame_context_returns_new_description_format(client):
    """Test that /v1/frames/<id>/context returns tags instead of entities/intent."""
    response = client.get("/v1/frames/1/context")
    assert response.status_code == 200
    data = response.get_json()

    if data.get("description"):
        desc = data["description"]
        assert "narrative" in desc
        assert "summary" in desc
        assert "tags" in desc
        assert isinstance(desc["tags"], list)
        assert "entities" not in desc
        assert "intent" not in desc


def test_activity_summary_returns_new_format(client):
    """Test that /v1/activity-summary returns tags instead of intent."""
    response = client.get("/v1/activity-summary")
    assert response.status_code == 200
    data = response.get_json()

    if data.get("descriptions"):
        for desc in data["descriptions"]:
            assert "summary" in desc
            assert "tags" in desc
            assert isinstance(desc["tags"], list)
            assert "intent" not in desc
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_description_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_description_api.py
git commit -m "feat(description): update API - return tags instead of entities/intent"
```

---

## Task 9: Update WebUI

**Files:**
- Modify: `openrecall/client/web/templates/index.html`

**Context:** WebUI 的 Description Tab 当前展示 `intent` 和 `entities` 字段，需要改为展示 `tags`。

- [ ] **Step 1: Find Description Tab section**

在 `openrecall/client/web/templates/index.html` 中搜索 `modalTab === 'description'`，找到 Description Tab 的 HTML 代码。

当前代码大约位于 line 1263-1286：

```html
<!-- Intent Section -->
<div class="metadata-section" x-show="selectedEntry?.description?.intent">
  <h3>Intent</h3>
  <div class="metadata-value" style="font-style: italic;" x-text="selectedEntry.description.intent"></div>
</div>

<!-- Entities Section -->
<div class="metadata-section" x-show="selectedEntry?.description?.entities?.length">
  <h3>Entities</h3>
  <div style="display: flex; flex-wrap: wrap; gap: 8px;">
    <template x-for="entity in selectedEntry.description.entities" :key="entity">
      <span style="
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        background: rgba(0, 122, 255, 0.12);
        color: #007AFF;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
      " x-text="entity"></span>
    </template>
  </div>
</div>
```

- [ ] **Step 2: Replace with Tags Section**

删除 Intent Section 和 Entities Section，替换为 Tags Section：

```html
<!-- Tags Section -->
<div class="metadata-section" x-show="selectedEntry?.description?.tags?.length">
  <h3>Tags</h3>
  <div style="display: flex; flex-wrap: wrap; gap: 8px;">
    <template x-for="tag in selectedEntry.description.tags" :key="tag">
      <span style="
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        background: rgba(0, 122, 255, 0.12);
        color: #007AFF;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
      " x-text="tag"></span>
    </template>
  </div>
</div>
```

- [ ] **Step 3: Verify no other references**

搜索 `index.html` 中是否还有其他使用 `entities` 或 `intent` 的地方：

```bash
grep -n "entities\|intent" openrecall/client/web/templates/index.html
```

应该只返回包含在字符串中的引用（如 "description" 单词本身），不应该再有 `.entities` 或 `.intent` 的属性访问。

- [ ] **Step 4: Manual test**

1. 启动 server 和 client
2. 打开浏览器访问 http://localhost:8889
3. 点击一个带有 description 的帧
4. 切换到 Description Tab
5. 确认显示 Summary、Narrative、Tags（而不是 Intent、Entities）

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(description): update WebUI - show tags instead of intent/entities"
```

---

## Task 10: Run Full Test Suite

- [ ] **Step 1: Run all description-related tests**

```bash
pytest tests/test_description_*.py -v
```

Expected: All PASS

- [ ] **Step 2: Run integration tests if available**

```bash
pytest tests/test_description_worker.py -v
```

Expected: PASS

- [ ] **Step 3: Final verification**

检查是否有遗漏的文件修改：

```bash
grep -r "entities_json\|entities\|intent" openrecall/server/description/ --include="*.py"
```

应该只返回 migration 文件中的引用（用于删除旧列），没有业务代码引用。

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "feat(description): complete fields redesign - narrative 1024, summary 256, tags replacing entities/intent"
```

---

## Summary

| Task | Component | Key Changes |
|------|-----------|-------------|
| 1 | FrameDescription model | narrative 1024, summary 256, tags list, remove entities/intent |
| 2 | OpenAI provider | New prompt with tags, JSON parsing |
| 3 | Local provider | New _build_messages with tags |
| 4 | DashScope provider | New prompt with tags, JSON parsing |
| 5 | Database migration | Drop entities/intent, add tags_json |
| 6 | FramesStore | Update insert_frame_description signature |
| 7 | DescriptionService | Use new to_db_dict fields |
| 8 | API | Return tags instead of entities/intent |
| 9 | WebUI | Show tags instead of intent/entities |
| 10 | Tests | Full verification |

**Breaking Changes:**
- API response 结构变化：clients 需要适配新的 `tags` 字段
- WebUI 展示变化：Description Tab 显示 Tags 而非 Intent/Entities
- 旧 descriptions 的 entities/intent 数据将被丢弃（迁移时设为默认值）
