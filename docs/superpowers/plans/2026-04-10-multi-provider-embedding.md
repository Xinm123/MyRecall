# Multi-Provider Embedding Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor embedding providers to support three distinct API formats: OpenAI (text-only), DashScope (skeleton), and custom multimodal API (qwen3-vl-embedding).

**Architecture:** Create three separate provider classes with distinct request formats. Factory selects provider by name (`openai`, `dashscope`, `multimodal`). Each provider implements `MultimodalEmbeddingProvider` protocol with `embed_image()` and `embed_text()` methods.

**Tech Stack:** Python, requests, numpy, pytest

---

## File Structure

```
openrecall/server/embedding/providers/
├── __init__.py          # Update exports
├── base.py              # No changes (existing protocol)
├── openai.py            # Refactor: rename class, text-only, clear error for images
├── dashscope.py         # Create: skeleton implementation
└── multimodal.py        # Create: qwen3-vl-embedding API provider

openrecall/server/ai/
└── factory.py           # Update: add provider selection logic

tests/
└── test_embedding_provider.py  # Update: add tests for new providers
```

---

## Task 1: Create QwenVLEmbeddingProvider (qwen3-vl-embedding API)

**Files:**
- Create: `openrecall/server/embedding/providers/multimodal.py`
- Test: `tests/test_embedding_provider.py`

### Step 1.1: Write failing test for QwenVLEmbeddingProvider initialization

Add to `tests/test_embedding_provider.py`:

```python
class TestQwenVLEmbeddingProvider:
    def test_init_allows_empty_api_key(self):
        """Empty api_key is allowed for local services without auth."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        provider = QwenVLEmbeddingProvider(
            api_key="", model_name="qwen3-vl-embedding", dimension=1024
        )
        assert provider.api_key == ""
        assert provider.model_name == "qwen3-vl-embedding"
        assert provider.dimension == 1024

    def test_init_requires_model_name(self):
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        with pytest.raises(EmbeddingProviderConfigError):
            QwenVLEmbeddingProvider(api_key="test", model_name="", dimension=1024)

    def test_init_normalizes_api_base(self):
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        provider = QwenVLEmbeddingProvider(
            api_key="test",
            model_name="test-model",
            api_base="http://localhost:8070/v1/",
            dimension=1024,
        )
        assert provider.api_base == "http://localhost:8070/v1"
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `pytest tests/test_embedding_provider.py::TestQwenVLEmbeddingProvider -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'openrecall.server.embedding.providers.multimodal'"

- [ ] **Step 1.3: Create multimodal.py with QwenVLEmbeddingProvider class**

Create `openrecall/server/embedding/providers/multimodal.py`:

```python
"""Qwen3-VL embedding provider for qwen3-vl-embedding API."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import requests

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
)
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _normalize_api_base(api_base: str) -> str:
    """Remove trailing slash from API base URL."""
    base = api_base.strip().strip("`\"' ")
    return base[:-1] if base.endswith("/") else base


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2 normalize a vector."""
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec.astype(np.float32, copy=False)
    return (vec / norm).astype(np.float32)


class QwenVLEmbeddingProvider(MultimodalEmbeddingProvider):
    """Qwen3-VL embedding provider for qwen3-vl-embedding API.

    Supports true fusion of text and image into a single embedding.

    API Format:
        POST /v1/embeddings/multimodal
        {
            "model": "qwen3-vl-embedding",
            "input": {
                "contents": [{"text": "...", "image": "<base64>"}]
            },
            "parameters": {"dimension": 1024}
        }

    Response Format:
        {
            "output": {
                "embeddings": [{"text_index": 0, "image_index": 0, "embedding": [...]}]
            },
            "dimension": 1024
        }
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
        dimension: int = 1024,
    ) -> None:
        if not model_name:
            raise EmbeddingProviderConfigError("model_name is required")

        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(
            api_base or "http://localhost:8070/v1"
        )
        self.dimension = dimension
        logger.info(
            f"QwenVLEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name} dim={self.dimension}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate fused embedding for image with optional text context.

        Args:
            image_path: Path to image file
            text: Optional text context (OCR/AX text)

        Returns:
            Normalized embedding vector (self.dimension dimensions)
        """
        path = Path(image_path).resolve()
        if not path.is_file():
            raise EmbeddingProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/embeddings/multimodal"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Build qwen3-vl-embedding API format
        content = {"image": encoded}
        if text and text.strip():
            content["text"] = text.strip()

        payload = {
            "model": self.model_name,
            "input": {
                "contents": [content]
            },
            "parameters": {
                "dimension": self.dimension
            }
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.ai_request_timeout,
            )
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: {e}"
            ) from e

        if not resp.ok:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: status={resp.status_code} "
                f"body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            # qwen3-vl-embedding response format
            embeddings = data.get("output", {}).get("embeddings", [])
            if not embeddings:
                raise EmbeddingProviderRequestError(
                    "No embedding in response"
                )
            emb = embeddings[0].get("embedding")
            if not isinstance(emb, list):
                raise EmbeddingProviderRequestError(
                    "Invalid embedding format in response"
                )
            vec = np.array(emb, dtype=np.float32)
            return _l2_normalize(vec)
        except EmbeddingProviderRequestError:
            raise
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Failed to parse embedding response: {e}"
            ) from e

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector (self.dimension dimensions)
        """
        if not text or text.isspace():
            return np.zeros(self.dimension, dtype=np.float32)

        url = f"{self.api_base}/embeddings/multimodal"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "input": {
                "contents": [{"text": text}]
            },
            "parameters": {
                "dimension": self.dimension
            }
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.ai_request_timeout,
            )
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: {e}"
            ) from e

        if not resp.ok:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: status={resp.status_code} "
                f"body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            embeddings = data.get("output", {}).get("embeddings", [])
            if not embeddings:
                raise EmbeddingProviderRequestError(
                    "No embedding in response"
                )
            emb = embeddings[0].get("embedding")
            if not isinstance(emb, list):
                raise EmbeddingProviderRequestError(
                    "Invalid embedding format in response"
                )
            vec = np.array(emb, dtype=np.float32)
            return _l2_normalize(vec)
        except EmbeddingProviderRequestError:
            raise
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Failed to parse embedding response: {e}"
            ) from e
```

- [ ] **Step 1.4: Run initialization tests**

Run: `pytest tests/test_embedding_provider.py::TestQwenVLEmbeddingProvider::test_init_allows_empty_api_key tests/test_embedding_provider.py::TestQwenVLEmbeddingProvider::test_init_requires_model_name tests/test_embedding_provider.py::TestQwenVLEmbeddingProvider::test_init_normalizes_api_base -v`
Expected: PASS

- [ ] **Step 1.5: Write failing test for embed_text**

Add to `tests/test_embedding_provider.py` in `TestQwenVLEmbeddingProvider`:

```python
    def test_embed_text_returns_normalized_vector(self):
        """embed_text should return normalized vector (L2 norm = 1)."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        provider = QwenVLEmbeddingProvider(
            api_key="test", model_name="test-model", dimension=1024
        )

        # Mock the API response - qwen3-vl-embedding format
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "output": {
                "embeddings": [{"text_index": 0, "image_index": -1, "embedding": [0.5] * 1024}]
            },
            "dimension": 1024
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = provider.embed_text("test query")

            # Verify qwen3-vl-embedding request format
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["model"] == "test-model"
            assert payload["input"]["contents"] == [{"text": "test query"}]
            assert payload["parameters"]["dimension"] == 1024

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001
```

- [ ] **Step 1.6: Run test to verify it passes**

Run: `pytest tests/test_embedding_provider.py::TestQwenVLEmbeddingProvider::test_embed_text_returns_normalized_vector -v`
Expected: PASS

- [ ] **Step 1.7: Write failing test for embed_image (fusion)**

Add to `tests/test_embedding_provider.py` in `TestQwenVLEmbeddingProvider`:

```python
    def test_embed_image_returns_normalized_vector(self, tmp_path):
        """embed_image should return normalized vector for fused image+text."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        provider = QwenVLEmbeddingProvider(
            api_key="test", model_name="test-model", dimension=1024
        )

        # Mock the API response - qwen3-vl-embedding format with fusion
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "output": {
                "embeddings": [
                    {"text_index": 0, "image_index": 0, "embedding": [0.5] * 1024}
                ]
            },
            "dimension": 1024
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            result = provider.embed_image(str(test_image), text="test context")

            # Verify qwen3-vl-embedding request format
            call_args = mock_post.call_args
            url = call_args[1]["url"] if "url" in call_args[1] else call_args[0][0]
            assert "/embeddings/multimodal" in url

            payload = call_args[1]["json"]
            content = payload["input"]["contents"][0]
            assert "image" in content
            assert content["text"] == "test context"
            assert payload["parameters"]["dimension"] == 1024

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001

    def test_embed_image_without_text_omits_text_field(self, tmp_path):
        """embed_image without text should only include image in content."""
        from openrecall.server.embedding.providers.multimodal import (
            QwenVLEmbeddingProvider,
        )

        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        provider = QwenVLEmbeddingProvider(
            api_key="test", model_name="test-model", dimension=1024
        )

        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "output": {
                "embeddings": [{"text_index": -1, "image_index": 0, "embedding": [0.5] * 1024}]
            }
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            provider.embed_image(str(test_image), text=None)

            payload = mock_post.call_args[1]["json"]
            content = payload["input"]["contents"][0]
            assert "image" in content
            assert "text" not in content
```

- [ ] **Step 1.8: Run tests to verify they pass**

Run: `pytest tests/test_embedding_provider.py::TestQwenVLEmbeddingProvider -v`
Expected: All PASS

- [ ] **Step 1.9: Commit QwenVLEmbeddingProvider**

```bash
git add openrecall/server/embedding/providers/multimodal.py tests/test_embedding_provider.py
git commit -m "feat(embedding): add QwenVLEmbeddingProvider for qwen3-vl-embedding API"
```

---

## Task 2: Refactor OpenAI Provider (Text-Only)

**Files:**
- Modify: `openrecall/server/embedding/providers/openai.py`
- Test: `tests/test_embedding_provider.py`

### Step 2.1: Write failing test for embed_image error

Add to `tests/test_embedding_provider.py` in `TestOpenAIEmbeddingProvider`:

```python
    def test_embed_image_raises_error(self, tmp_path):
        """embed_image should raise error - OpenAI doesn't support image embedding."""
        from openrecall.server.embedding.providers.openai import (
            OpenAIEmbeddingProvider,
        )

        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        provider = OpenAIEmbeddingProvider(
            api_key="test", model_name="text-embedding-3-small"
        )

        with pytest.raises(EmbeddingProviderRequestError) as exc_info:
            provider.embed_image(str(test_image))

        assert "OpenAI does not support image embedding" in str(exc_info.value)
        assert "multimodal" in str(exc_info.value)
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `pytest tests/test_embedding_provider.py::TestOpenAIEmbeddingProvider::test_embed_image_raises_error -v`
Expected: FAIL (current implementation tries to call API)

- [ ] **Step 2.3: Refactor openai.py - rename class and add image error**

Replace `openrecall/server/embedding/providers/openai.py`:

```python
"""OpenAI text embedding provider."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import requests

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
)
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _normalize_api_base(api_base: str) -> str:
    """Remove trailing slash from API base URL."""
    base = api_base.strip().strip("`\"' ")
    return base[:-1] if base.endswith("/") else base


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2 normalize a vector."""
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        return vec.astype(np.float32, copy=False)
    return (vec / norm).astype(np.float32)


# Backwards compatibility alias
OpenAIMultimodalEmbeddingProvider: type


class OpenAIEmbeddingProvider(MultimodalEmbeddingProvider):
    """OpenAI text embedding provider.

    Supports OpenAI official /v1/embeddings API (text only).
    For multimodal embedding, use 'multimodal' or 'dashscope' provider.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not model_name:
            raise EmbeddingProviderConfigError("model_name is required")

        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(
            api_base or "https://api.openai.com/v1"
        )
        logger.info(
            f"OpenAIEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """OpenAI does not support image embedding.

        Raises:
            EmbeddingProviderRequestError: Always, with guidance to use
                'multimodal' or 'dashscope' provider.
        """
        raise EmbeddingProviderRequestError(
            "OpenAI does not support image embedding. "
            "Use 'multimodal' or 'dashscope' provider."
        )

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector
        """
        if not text or text.isspace():
            return np.zeros(1024, dtype=np.float32)

        url = f"{self.api_base}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "input": text,
            "encoding_format": "float",
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.ai_request_timeout,
            )
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: {e}"
            ) from e

        if not resp.ok:
            raise EmbeddingProviderRequestError(
                f"Embedding request failed: status={resp.status_code} "
                f"body={resp.text[:500]}"
            )

        try:
            data = resp.json()
            items = data.get("data") or []
            if not items:
                raise EmbeddingProviderRequestError(
                    "No embedding in response"
                )
            emb = items[0].get("embedding")
            if not isinstance(emb, list):
                raise EmbeddingProviderRequestError(
                    "Invalid embedding format in response"
                )
            vec = np.array(emb, dtype=np.float32)
            return _l2_normalize(vec)
        except EmbeddingProviderRequestError:
            raise
        except Exception as e:
            raise EmbeddingProviderRequestError(
                f"Failed to parse embedding response: {e}"
            ) from e


# Backwards compatibility alias
OpenAIMultimodalEmbeddingProvider = OpenAIEmbeddingProvider
```

- [ ] **Step 2.4: Update test class name**

In `tests/test_embedding_provider.py`, rename the test class from `TestOpenAIMultimodalEmbeddingProvider` to `TestOpenAIEmbeddingProvider` and update all imports from:

```python
from openrecall.server.embedding.providers.openai import (
    OpenAIMultimodalEmbeddingProvider,
)
```

To:

```python
from openrecall.server.embedding.providers.openai import (
    OpenAIEmbeddingProvider,
)
```

And update all provider instantiations from `OpenAIMultimodalEmbeddingProvider` to `OpenAIEmbeddingProvider`.

- [ ] **Step 2.5: Run all OpenAI provider tests**

Run: `pytest tests/test_embedding_provider.py::TestOpenAIEmbeddingProvider -v`
Expected: All PASS

- [ ] **Step 2.6: Commit OpenAI provider refactor**

```bash
git add openrecall/server/embedding/providers/openai.py tests/test_embedding_provider.py
git commit -m "refactor(embedding): rename to OpenAIEmbeddingProvider, text-only support"
```

---

## Task 3: Create DashScope Provider Skeleton

**Files:**
- Create: `openrecall/server/embedding/providers/dashscope.py`
- Test: `tests/test_embedding_provider.py`

### Step 3.1: Write failing test for DashScope provider skeleton

Add to `tests/test_embedding_provider.py`:

```python
class TestDashScopeEmbeddingProvider:
    def test_init_allows_empty_api_key_for_local(self):
        """Empty api_key is allowed for testing."""
        from openrecall.server.embedding.providers.dashscope import (
            DashScopeEmbeddingProvider,
        )

        provider = DashScopeEmbeddingProvider(
            api_key="", model_name="text-embedding-v3"
        )
        assert provider.api_key == ""
        assert provider.model_name == "text-embedding-v3"

    def test_init_requires_model_name(self):
        from openrecall.server.embedding.providers.dashscope import (
            DashScopeEmbeddingProvider,
        )

        with pytest.raises(EmbeddingProviderConfigError):
            DashScopeEmbeddingProvider(api_key="test", model_name="")

    def test_embed_image_raises_not_implemented(self, tmp_path):
        """embed_image should raise NotImplementedError - not yet implemented."""
        from openrecall.server.embedding.providers.dashscope import (
            DashScopeEmbeddingProvider,
        )

        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        provider = DashScopeEmbeddingProvider(
            api_key="test", model_name="text-embedding-v3"
        )

        with pytest.raises(NotImplementedError) as exc_info:
            provider.embed_image(str(test_image))

        assert "not yet implemented" in str(exc_info.value)

    def test_embed_text_raises_not_implemented(self):
        """embed_text should raise NotImplementedError - not yet implemented."""
        from openrecall.server.embedding.providers.dashscope import (
            DashScopeEmbeddingProvider,
        )

        provider = DashScopeEmbeddingProvider(
            api_key="test", model_name="text-embedding-v3"
        )

        with pytest.raises(NotImplementedError) as exc_info:
            provider.embed_text("test query")

        assert "not yet implemented" in str(exc_info.value)
```

- [ ] **Step 3.2: Run test to verify it fails**

Run: `pytest tests/test_embedding_provider.py::TestDashScopeEmbeddingProvider -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3.3: Create dashscope.py skeleton**

Create `openrecall/server/embedding/providers/dashscope.py`:

```python
"""DashScope native API embedding provider (skeleton)."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderConfigError,
)

logger = logging.getLogger(__name__)


class DashScopeEmbeddingProvider(MultimodalEmbeddingProvider):
    """DashScope native API embedding provider.

    Implementation pending. Will support DashScope's native API format.
    See: https://help.aliyun.com/document_detail/2712537.html

    For now, use 'multimodal' provider with DashScope's OpenAI-compatible mode.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = "",
    ) -> None:
        if not model_name:
            raise EmbeddingProviderConfigError("model_name is required")

        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = api_base.strip() if api_base else "https://dashscope.aliyuncs.com/api/v1"
        logger.info(
            f"DashScopeEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Not yet implemented. Will use DashScope native multimodal API.
        """
        raise NotImplementedError(
            "DashScope multimodal embedding not yet implemented. "
            "Use 'multimodal' provider with DashScope's OpenAI-compatible mode, "
            "or check https://help.aliyun.com/document_detail/2712537.html"
        )

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Not yet implemented. Will use DashScope native text embedding API.
        """
        raise NotImplementedError(
            "DashScope text embedding not yet implemented. "
            "Use 'multimodal' provider with DashScope's OpenAI-compatible mode, "
            "or check https://help.aliyun.com/document_detail/2712537.html"
        )
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `pytest tests/test_embedding_provider.py::TestDashScopeEmbeddingProvider -v`
Expected: All PASS

- [ ] **Step 3.5: Commit DashScope provider skeleton**

```bash
git add openrecall/server/embedding/providers/dashscope.py tests/test_embedding_provider.py
git commit -m "feat(embedding): add DashScopeEmbeddingProvider skeleton"
```

---

## Task 4: Update Provider Exports

**Files:**
- Modify: `openrecall/server/embedding/providers/__init__.py`

### Step 4.1: Update __init__.py exports

Replace `openrecall/server/embedding/providers/__init__.py`:

```python
"""Embedding providers for multimodal vector generation."""
from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)
from openrecall.server.embedding.providers.openai import (
    OpenAIEmbeddingProvider,
    OpenAIMultimodalEmbeddingProvider,  # Backwards compatibility alias
)
from openrecall.server.embedding.providers.dashscope import (
    DashScopeEmbeddingProvider,
)
from openrecall.server.embedding.providers.multimodal import (
    QwenVLEmbeddingProvider,
)

__all__ = [
    # Protocol and errors
    "MultimodalEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigError",
    "EmbeddingProviderRequestError",
    "EmbeddingProviderUnavailableError",
    # Providers
    "OpenAIEmbeddingProvider",
    "OpenAIMultimodalEmbeddingProvider",  # Alias for backwards compat
    "DashScopeEmbeddingProvider",
    "QwenVLEmbeddingProvider",
]
```

- [ ] **Step 4.2: Verify imports work**

Run: `python -c "from openrecall.server.embedding.providers import OpenAIEmbeddingProvider, DashScopeEmbeddingProvider, QwenVLEmbeddingProvider; print('OK')"`
Expected: "OK"

- [ ] **Step 4.3: Commit exports update**

```bash
git add openrecall/server/embedding/providers/__init__.py
git commit -m "feat(embedding): export all embedding providers"
```

---

## Task 5: Update Factory Provider Selection

**Files:**
- Modify: `openrecall/server/ai/factory.py`

### Step 5.1: Update get_multimodal_embedding_provider function

Replace the `get_multimodal_embedding_provider` function in `openrecall/server/ai/factory.py` (lines 176-203):

```python
def get_multimodal_embedding_provider() -> "MultimodalEmbeddingProvider":
    """Get or create a cached MultimodalEmbeddingProvider instance.

    Supports providers: openai, dashscope, multimodal
    """
    from openrecall.server.embedding.providers import (
        MultimodalEmbeddingProvider,
        OpenAIEmbeddingProvider,
        DashScopeEmbeddingProvider,
        QwenVLEmbeddingProvider,
    )

    capability = "multimodal_embedding"
    cached = _instances.get(capability)
    if cached is not None:
        return cached  # type: ignore[return-value]

    provider = settings.embedding_provider.strip().lower() if settings.embedding_provider else "openai"
    model_name = settings.embedding_model
    api_key = settings.embedding_api_key
    api_base = settings.embedding_api_base
    dimension = settings.embedding_dim

    if provider == "openai":
        instance: MultimodalEmbeddingProvider = OpenAIEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    elif provider == "dashscope":
        instance = DashScopeEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    elif provider == "multimodal":
        instance = QwenVLEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
            dimension=dimension,
        )
    else:
        raise AIProviderConfigError(f"Unknown embedding provider: {provider}")

    _instances[capability] = instance
    return instance
```

- [ ] **Step 5.2: Run factory tests**

Run: `pytest tests/ -k "embedding" -v --tb=short`
Expected: All PASS

- [ ] **Step 5.3: Commit factory update**

```bash
git add openrecall/server/ai/factory.py
git commit -m "feat(embedding): add provider selection in factory"
```

---

## Task 6: Final Verification

### Step 6.1: Run all embedding tests

Run: `pytest tests/test_embedding*.py -v`
Expected: All PASS

- [ ] **Step 6.2: Run full test suite**

Run: `pytest tests/ -v --tb=short -x`
Expected: All PASS (or skip known failing tests)

- [ ] **Step 6.3: Final commit with all changes**

```bash
git add -A
git commit -m "feat(embedding): multi-provider architecture complete

- OpenAIEmbeddingProvider: text-only, clear error for images
- DashScopeEmbeddingProvider: skeleton for future implementation
- QwenVLEmbeddingProvider: qwen3-vl-embedding API with true fusion
- Factory supports provider selection: openai, dashscope, multimodal
- Dimension configurable via embedding.dim setting (default 1024)"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Create QwenVLEmbeddingProvider | `providers/multimodal.py` (new), tests |
| 2 | Refactor OpenAI provider | `providers/openai.py`, tests |
| 3 | Create DashScope skeleton | `providers/dashscope.py` (new), tests |
| 4 | Update exports | `providers/__init__.py` |
| 5 | Update factory | `ai/factory.py` |
| 6 | Final verification | - |
