# Frame Embedding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multimodal embedding support for frames using qwen3-vl-embedding, enabling semantic search and similar frame lookup.

**Architecture:** Single fused embedding (image + OCR/AX text) stored in LanceDB. Independent EmbeddingWorker runs parallel to DescriptionWorker. Hybrid search combines FTS5 and vector search using RRF fusion.

**Tech Stack:** Python, LanceDB, SQLite, OpenAI-compatible API, Pydantic, Flask

---

## File Structure

```
openrecall/server/
├── embedding/                         # NEW MODULE
│   ├── __init__.py                   # Exports
│   ├── models.py                     # FrameEmbedding Pydantic model
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                   # MultimodalEmbeddingProvider protocol + errors
│   │   └── openai.py                 # OpenAI-compatible provider
│   ├── service.py                    # EmbeddingService
│   └── worker.py                     # EmbeddingWorker
├── database/
│   ├── migrations/
│   │   └── 20260409120000_add_frame_embedding.sql  # NEW
│   └── embedding_store.py            # NEW: LanceDB store
├── search/
│   └── hybrid_engine.py              # NEW: RRF fusion
└── api_v1.py                         # EXTEND: New endpoints

tests/
├── test_embedding_models.py          # NEW
├── test_embedding_provider.py        # NEW
├── test_embedding_store.py           # NEW
├── test_embedding_worker.py          # NEW
├── test_hybrid_search.py             # NEW
└── test_embedding_api.py             # NEW
```

---

## Task 1: Database Migration

**Files:**
- Create: `openrecall/server/database/migrations/20260409120000_add_frame_embedding.sql`

- [ ] **Step 1: Create migration file**

```sql
-- Migration: 20260409120000_add_frame_embedding.sql
-- Created: 2026-04-09
-- Purpose: Add frame embedding support for multimodal vector search
-- Tables: embedding_tasks (task queue for embedding generation),
--         frames.embedding_status (tracks embedding generation state)
-- Note: Transaction is managed by migrations_runner.py, do not add BEGIN/COMMIT here.

-- 1. Add embedding_status to frames table
ALTER TABLE frames ADD COLUMN embedding_status TEXT DEFAULT NULL;

-- 2. Create embedding_tasks table
CREATE TABLE IF NOT EXISTS embedding_tasks (
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

CREATE INDEX IF NOT EXISTS idx_emb_task_status ON embedding_tasks(status);
CREATE INDEX IF NOT EXISTS idx_emb_task_next_retry ON embedding_tasks(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_emb_task_frame_id ON embedding_tasks(frame_id);
```

- [ ] **Step 2: Run migration test**

Run: `pytest tests/test_v3_migrations_bootstrap.py -v`
Expected: PASS (migration runs on test db)

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/database/migrations/20260409120000_add_frame_embedding.sql
git commit -m "feat(db): add embedding_tasks table and frames.embedding_status column"
```

---

## Task 2: Embedding Models

**Files:**
- Create: `openrecall/server/embedding/__init__.py`
- Create: `openrecall/server/embedding/models.py`
- Create: `tests/test_embedding_models.py`

- [ ] **Step 1: Create embedding module init**

```python
# openrecall/server/embedding/__init__.py
"""Frame embedding module for multimodal vector search."""
from openrecall.server.embedding.models import FrameEmbedding

__all__ = ["FrameEmbedding"]
```

- [ ] **Step 2: Write failing test for FrameEmbedding model**

```python
# tests/test_embedding_models.py
"""Tests for embedding models."""
import pytest
from openrecall.server.embedding.models import FrameEmbedding


class TestFrameEmbedding:
    def test_frame_embedding_creation(self):
        emb = FrameEmbedding(
            frame_id=123,
            embedding_vector=[0.1] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="Chrome",
            window_name="GitHub",
        )
        assert emb.frame_id == 123
        assert emb.embedding_model == "qwen3-vl-embedding"
        assert emb.app_name == "Chrome"
        assert emb.window_name == "GitHub"

    def test_frame_embedding_defaults(self):
        emb = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.0] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        assert emb.app_name == ""
        assert emb.window_name == ""
        assert emb.embedding_model == "qwen3-vl-embedding"

    def test_frame_embedding_to_dict(self):
        emb = FrameEmbedding(
            frame_id=42,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="VSCode",
        )
        d = emb.to_storage_dict()
        assert d["frame_id"] == 42
        assert d["app_name"] == "VSCode"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_embedding_models.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 4: Create FrameEmbedding model**

```python
# openrecall/server/embedding/models.py
"""Embedding models for frame vector storage."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class FrameEmbedding(BaseModel):
    """Frame embedding for LanceDB storage.

    Stores multimodal (image + text) embedding for a frame.
    """

    frame_id: int = Field(description="Reference to frames.id")
    embedding_vector: List[float] = Field(
        description="Multimodal embedding vector (1024 dimensions)"
    )
    embedding_model: str = Field(
        default="qwen3-vl-embedding",
        description="Model used to generate embedding",
    )

    # Redundant metadata for filtering without JOIN
    timestamp: str = Field(description="Frame timestamp (ISO8601 UTC)")
    app_name: str = Field(default="", description="Application name")
    window_name: str = Field(default="", description="Window title")

    def to_storage_dict(self) -> dict:
        """Convert to dict for LanceDB storage."""
        return {
            "frame_id": self.frame_id,
            "embedding_vector": self.embedding_vector,
            "embedding_model": self.embedding_model,
            "timestamp": self.timestamp,
            "app_name": self.app_name,
            "window_name": self.window_name,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_embedding_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/embedding/__init__.py
git add openrecall/server/embedding/models.py
git add tests/test_embedding_models.py
git commit -m "feat(embedding): add FrameEmbedding model"
```

---

## Task 3: Embedding Provider Protocol

**Files:**
- Create: `openrecall/server/embedding/providers/__init__.py`
- Create: `openrecall/server/embedding/providers/base.py`
- Create: `tests/test_embedding_provider.py` (partial: protocol tests)

- [ ] **Step 1: Create providers init**

```python
# openrecall/server/embedding/providers/__init__.py
"""Embedding providers for multimodal vector generation."""
from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)

__all__ = [
    "MultimodalEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigError",
    "EmbeddingProviderRequestError",
    "EmbeddingProviderUnavailableError",
]
```

- [ ] **Step 2: Write failing test for provider errors**

```python
# tests/test_embedding_provider.py
"""Tests for embedding providers."""
import pytest

from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)


class TestEmbeddingProviderErrors:
    def test_error_hierarchy(self):
        assert issubclass(EmbeddingProviderConfigError, EmbeddingProviderError)
        assert issubclass(EmbeddingProviderRequestError, EmbeddingProviderError)
        assert issubclass(EmbeddingProviderUnavailableError, EmbeddingProviderError)

    def test_can_raise_and_catch_errors(self):
        with pytest.raises(EmbeddingProviderError):
            raise EmbeddingProviderError("test")
        with pytest.raises(EmbeddingProviderConfigError):
            raise EmbeddingProviderConfigError("config error")

    def test_config_error_requires_model_name(self):
        """ConfigError should be raised when model_name is missing."""
        pass  # Will test with OpenAI provider
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_embedding_provider.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 4: Create provider protocol and errors**

```python
# openrecall/server/embedding/providers/base.py
"""Embedding provider protocol and errors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class EmbeddingProviderError(Exception):
    """Base error for embedding providers."""
    pass


class EmbeddingProviderConfigError(EmbeddingProviderError):
    """Configuration error."""
    pass


class EmbeddingProviderRequestError(EmbeddingProviderError):
    """Request/execution error."""
    pass


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Provider unavailable (missing dependency, etc)."""
    pass


class MultimodalEmbeddingProvider(ABC):
    """Protocol for multimodal embedding providers.

    Supports both image+text fusion embedding and text-only embedding.
    """

    @abstractmethod
    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Args:
            image_path: Path to image file (JPEG/PNG)
            text: Optional text context (OCR/AX text from frame.full_text)

        Returns:
            Normalized embedding vector (1024 dimensions)

        Raises:
            EmbeddingProviderRequestError: On API/SDK error
            EmbeddingProviderUnavailableError: On missing dependencies
        """
        raise NotImplementedError

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text for semantic search

        Returns:
            Normalized embedding vector (1024 dimensions)

        Raises:
            EmbeddingProviderRequestError: On API/SDK error
        """
        raise NotImplementedError
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_embedding_provider.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/embedding/providers/__init__.py
git add openrecall/server/embedding/providers/base.py
git add tests/test_embedding_provider.py
git commit -m "feat(embedding): add MultimodalEmbeddingProvider protocol and errors"
```

---

## Task 4: OpenAI-Compatible Embedding Provider

**Files:**
- Modify: `openrecall/server/embedding/providers/__init__.py`
- Create: `openrecall/server/embedding/providers/openai.py`
- Modify: `tests/test_embedding_provider.py`

- [ ] **Step 1: Add test for OpenAI provider initialization**

```python
# Add to tests/test_embedding_provider.py

class TestOpenAIMultimodalEmbeddingProvider:
    def test_init_allows_empty_api_key_for_local_vllm(self):
        """Empty api_key is allowed for local vLLM without auth."""
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        provider = OpenAIMultimodalEmbeddingProvider(
            api_key="", model_name="qwen3-vl-embedding"
        )
        assert provider.api_key == ""
        assert provider.model_name == "qwen3-vl-embedding"

    def test_init_requires_model_name(self):
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        with pytest.raises(EmbeddingProviderConfigError):
            OpenAIMultimodalEmbeddingProvider(api_key="sk-test", model_name="")

    def test_init_normalizes_api_base(self):
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        provider = OpenAIMultimodalEmbeddingProvider(
            api_key="test",
            model_name="test-model",
            api_base="http://localhost:8000/v1/",
        )
        assert provider.api_base == "http://localhost:8000/v1"

    def test_embed_text_returns_normalized_vector(self):
        """embed_text should return normalized vector (L2 norm = 1)."""
        import numpy as np
        from unittest.mock import patch, Mock
        from openrecall.server.embedding.providers.openai import (
            OpenAIMultimodalEmbeddingProvider,
        )

        provider = OpenAIMultimodalEmbeddingProvider(
            api_key="test", model_name="test-model"
        )

        # Mock the API response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "data": [{"embedding": [0.5] * 1024}]
        }

        with patch("requests.post", return_value=mock_response):
            result = provider.embed_text("test query")

        assert isinstance(result, np.ndarray)
        assert result.shape == (1024,)
        # Check L2 normalization
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 0.001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embedding_provider.py::TestOpenAIMultimodalEmbeddingProvider -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Implement OpenAI provider**

```python
# openrecall/server/embedding/providers/openai.py
"""OpenAI-compatible multimodal embedding provider."""
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


class OpenAIMultimodalEmbeddingProvider(MultimodalEmbeddingProvider):
    """OpenAI-compatible multimodal embedding provider.

    Supports cloud APIs (OpenAI, DashScope) and local network services (vLLM).
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
            f"OpenAIMultimodalEmbeddingProvider initialized: "
            f"base={self.api_base} model={self.model_name}"
        )

    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Args:
            image_path: Path to image file
            text: Optional text context (OCR/AX text)

        Returns:
            Normalized embedding vector
        """
        path = Path(image_path).resolve()
        if not path.is_file():
            raise EmbeddingProviderRequestError(f"Image not found: {image_path}")

        image_bytes = path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        url = f"{self.api_base}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Build multimodal input
        # NOTE: API format varies by provider. This implementation supports:
        # 1. OpenAI-style text-only: {"input": "text", ...}
        # 2. Multimodal with image+text (provider-specific):
        #    - Some providers use: {"input": {"image": "...", "text": "..."}}
        #    - Others use: {"input": [...], "modalities": ["image", "text"]}
        #
        # For qwen3-vl-embedding via vLLM/DashScope, verify the exact format.
        # Current implementation uses a generic format that may need adjustment.
        input_data = {
            "image": f"data:image/jpeg;base64,{encoded}",
        }
        if text:
            input_data["text"] = text

        payload = {
            "model": self.model_name,
            "input": input_data,
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

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector
        """
        if not text or text.isspace():
            # Return zero vector for empty text
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
```

- [ ] **Step 4: Update providers __init__.py**

```python
# openrecall/server/embedding/providers/__init__.py
"""Embedding providers for multimodal vector generation."""
from openrecall.server.embedding.providers.base import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderConfigError,
    EmbeddingProviderRequestError,
    EmbeddingProviderUnavailableError,
)
from openrecall.server.embedding.providers.openai import (
    OpenAIMultimodalEmbeddingProvider,
)

__all__ = [
    "MultimodalEmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigError",
    "EmbeddingProviderRequestError",
    "EmbeddingProviderUnavailableError",
    "OpenAIMultimodalEmbeddingProvider",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_embedding_provider.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/embedding/providers/
git add tests/test_embedding_provider.py
git commit -m "feat(embedding): add OpenAI-compatible multimodal embedding provider"
```

---

## Task 5: Embedding Store (LanceDB)

**Files:**
- Create: `openrecall/server/database/embedding_store.py`
- Create: `tests/test_embedding_store.py`

- [ ] **Step 1: Write failing test for EmbeddingStore**

```python
# tests/test_embedding_store.py
"""Tests for embedding store (LanceDB)."""
import tempfile
import shutil
from pathlib import Path

import pytest

from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.database.embedding_store import EmbeddingStore


class TestEmbeddingStore:
    def test_init_creates_table(self, tmp_path):
        """Store initialization should create the table."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))
        # Should not raise
        assert store.table_name == "frame_embeddings"

    def test_save_and_search_embedding(self, tmp_path):
        """Should save embedding and search by similarity."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        # Create embedding
        emb = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.1] * 1024,
            timestamp="2026-04-09T12:00:00Z",
            app_name="Chrome",
            window_name="GitHub",
        )

        # Save
        store.save_embedding(emb)

        # Search with same vector
        results = store.search([0.1] * 1024, limit=5)

        assert len(results) == 1
        assert results[0].frame_id == 1

    def test_search_returns_multiple_results(self, tmp_path):
        """Search should return multiple results sorted by similarity."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        # Save two embeddings with different vectors
        emb1 = FrameEmbedding(
            frame_id=1,
            embedding_vector=[0.9] * 1024,  # High values
            timestamp="2026-04-09T12:00:00Z",
        )
        emb2 = FrameEmbedding(
            frame_id=2,
            embedding_vector=[0.1] * 1024,  # Low values
            timestamp="2026-04-09T12:01:00Z",
        )
        store.save_embedding(emb1)
        store.save_embedding(emb2)

        # Search with high-value vector should return emb1 first
        results = store.search([0.9] * 1024, limit=10)
        assert len(results) == 2
        assert results[0].frame_id == 1  # Higher similarity

    def test_get_embedding_by_frame_id(self, tmp_path):
        """Should retrieve embedding by frame_id."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))

        emb = FrameEmbedding(
            frame_id=42,
            embedding_vector=[0.5] * 1024,
            timestamp="2026-04-09T12:00:00Z",
        )
        store.save_embedding(emb)

        result = store.get_by_frame_id(42)
        assert result is not None
        assert result.frame_id == 42

    def test_get_embedding_not_found(self, tmp_path):
        """Should return None for non-existent frame_id."""
        store = EmbeddingStore(db_path=str(tmp_path / "test_embeddings"))
        result = store.get_by_frame_id(999)
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embedding_store.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement EmbeddingStore**

```python
# openrecall/server/database/embedding_store.py
"""LanceDB store for frame embeddings."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import lancedb
import numpy as np
from lancedb.pydantic import LanceModel, Vector
from pydantic import Field

from openrecall.server.embedding.models import FrameEmbedding

logger = logging.getLogger(__name__)


class FrameEmbeddingSchema(LanceModel):
    """LanceDB schema for frame embeddings."""

    frame_id: int = Field(description="Reference to frames.id")
    embedding_vector: Vector(1024) = Field(
        description="Multimodal embedding vector"
    )
    embedding_model: str = Field(
        default="qwen3-vl-embedding",
        description="Model used to generate embedding",
    )
    timestamp: str = Field(description="Frame timestamp (ISO8601 UTC)")
    app_name: str = Field(default="", description="Application name")
    window_name: str = Field(default="", description="Window title")


class EmbeddingStore:
    """LanceDB storage for frame embeddings."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        table_name: str = "frame_embeddings",
    ):
        """Initialize the embedding store.

        Args:
            db_path: Path to LanceDB database. Defaults to settings.lancedb_path.
            table_name: Table name for embeddings.
        """
        from openrecall.shared.config import settings

        self.db_path = Path(db_path or settings.lancedb_path)
        self.table_name = table_name

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db = lancedb.connect(str(self.db_path))
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the table with schema if it doesn't exist."""
        existing_tables = self.db.list_tables()

        if self.table_name not in existing_tables:
            logger.info(f"Creating LanceDB table '{self.table_name}'")
            try:
                self.db.create_table(
                    self.table_name, schema=FrameEmbeddingSchema
                )
            except ValueError as e:
                if "already exists" in str(e):
                    pass
                else:
                    raise
        else:
            # Table exists, validate by opening
            try:
                self.db.open_table(self.table_name)
            except Exception as e:
                logger.warning(
                    f"Schema mismatch for table '{self.table_name}': {e}"
                )
                logger.warning("Dropping and recreating table...")
                self.db.drop_table(self.table_name)
                self.db.create_table(
                    self.table_name, schema=FrameEmbeddingSchema
                )

    def save_embedding(self, embedding: FrameEmbedding) -> None:
        """Save a frame embedding to the store.

        Args:
            embedding: FrameEmbedding to save
        """
        table = self.db.open_table(self.table_name)

        # Check if embedding already exists for this frame
        existing = self.get_by_frame_id(embedding.frame_id)
        if existing is not None:
            # Delete existing embedding
            table.delete(f"frame_id = {embedding.frame_id}")

        # Add new embedding
        table.add([embedding.to_storage_dict()])
        logger.debug(f"Saved embedding for frame_id={embedding.frame_id}")

    def search(
        self,
        query_vector: List[float],
        limit: int = 20,
    ) -> List[FrameEmbedding]:
        """Search for similar embeddings.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results

        Returns:
            List of FrameEmbedding sorted by similarity (highest first)
        """
        table = self.db.open_table(self.table_name)

        query = table.search(query_vector)

        # Try to use cosine metric if available
        metric_fn = getattr(query, "metric", None)
        if callable(metric_fn):
            try:
                query = query.metric("cosine")
            except Exception:
                pass

        results = query.limit(limit).to_list()

        # Convert to FrameEmbedding objects
        embeddings = []
        for r in results:
            emb = FrameEmbedding(
                frame_id=r["frame_id"],
                embedding_vector=r["embedding_vector"],
                embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
                timestamp=r["timestamp"],
                app_name=r.get("app_name", ""),
                window_name=r.get("window_name", ""),
            )
            embeddings.append(emb)

        return embeddings

    def get_by_frame_id(self, frame_id: int) -> Optional[FrameEmbedding]:
        """Get embedding by frame_id.

        Args:
            frame_id: Frame ID to look up

        Returns:
            FrameEmbedding if found, None otherwise
        """
        table = self.db.open_table(self.table_name)

        results = table.search().where(f"frame_id = {frame_id}").limit(1).to_list()

        if not results:
            return None

        r = results[0]
        return FrameEmbedding(
            frame_id=r["frame_id"],
            embedding_vector=r["embedding_vector"],
            embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
            timestamp=r["timestamp"],
            app_name=r.get("app_name", ""),
            window_name=r.get("window_name", ""),
        )

    def delete_by_frame_id(self, frame_id: int) -> None:
        """Delete embedding by frame_id.

        Args:
            frame_id: Frame ID to delete
        """
        table = self.db.open_table(self.table_name)
        table.delete(f"frame_id = {frame_id}")
        logger.debug(f"Deleted embedding for frame_id={frame_id}")

    def count(self) -> int:
        """Return total number of embeddings."""
        table = self.db.open_table(self.table_name)
        return len(table)

    def search_with_distance(
        self,
        query_vector: List[float],
        limit: int = 20,
    ) -> List[Tuple[FrameEmbedding, float]]:
        """Search for similar embeddings and return with distance scores.

        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results

        Returns:
            List of (FrameEmbedding, distance) tuples sorted by distance (ascending)
        """
        table = self.db.open_table(self.table_name)

        query = table.search(query_vector)

        # Try to use cosine metric if available
        metric_fn = getattr(query, "metric", None)
        if callable(metric_fn):
            try:
                query = query.metric("cosine")
            except Exception:
                pass

        # Get results with distance column
        results = query.limit(limit).to_list()

        # Convert to (FrameEmbedding, distance) tuples
        embeddings_with_distance = []
        for r in results:
            emb = FrameEmbedding(
                frame_id=r["frame_id"],
                embedding_vector=r["embedding_vector"],
                embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
                timestamp=r["timestamp"],
                app_name=r.get("app_name", ""),
                window_name=r.get("window_name", ""),
            )
            # LanceDB returns distance in _distance column
            distance = r.get("_distance", 0.0)
            embeddings_with_distance.append((emb, distance))

        return embeddings_with_distance
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_embedding_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/embedding_store.py
git add tests/test_embedding_store.py
git commit -m "feat(db): add EmbeddingStore for LanceDB vector storage"
```

---

## Task 6: Embedding Service

**Files:**
- Create: `openrecall/server/embedding/service.py`
- Create: `tests/test_embedding_service.py`

- [ ] **Step 1: Write failing test for EmbeddingService**

```python
# tests/test_embedding_service.py
"""Tests for embedding service."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.embedding.service import EmbeddingService


class TestEmbeddingService:
    def test_enqueue_embedding_task(self, tmp_path):
        """Should insert a pending embedding task."""
        # Create a test database
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                embedding_status TEXT DEFAULT NULL
            );
            CREATE TABLE embedding_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(frame_id)
            );
            INSERT INTO frames (id) VALUES (1), (2);
        """)
        conn.commit()

        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)

        service = EmbeddingService(store=store)

        # Enqueue task
        service.enqueue_embedding_task(conn, frame_id=1)

        # Verify task was created
        row = conn.execute(
            "SELECT * FROM embedding_tasks WHERE frame_id = 1"
        ).fetchone()
        assert row is not None
        assert row[2] == "pending"  # status column

        conn.close()

    def test_get_queue_status(self, tmp_path):
        """Should return queue statistics."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                embedding_status TEXT DEFAULT NULL
            );
            CREATE TABLE embedding_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(frame_id)
            );
            INSERT INTO frames (id) VALUES (1), (2), (3);
            INSERT INTO embedding_tasks (frame_id, status) VALUES
                (1, 'pending'),
                (2, 'processing'),
                (3, 'completed');
        """)
        conn.commit()

        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)

        service = EmbeddingService(store=store)
        status = service.get_queue_status(conn)

        assert status["pending"] == 1
        assert status["processing"] == 1
        assert status["completed"] == 1

        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embedding_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement EmbeddingService**

```python
# openrecall/server/embedding/service.py
"""Embedding service: enqueue, generate, backfill."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.embedding.providers import (
    MultimodalEmbeddingProvider,
    EmbeddingProviderError,
)

if TYPE_CHECKING:
    from openrecall.server.database.frames_store import FramesStore
    from openrecall.server.database.embedding_store import EmbeddingStore

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min
_MAX_RETRIES = 3


class EmbeddingService:
    """Service for frame embedding operations."""

    def __init__(
        self,
        store: "FramesStore",
        embedding_store: Optional["EmbeddingStore"] = None,
        provider: Optional[MultimodalEmbeddingProvider] = None,
    ) -> None:
        self._store = store
        self._embedding_store = embedding_store
        self._provider = provider

    @property
    def embedding_store(self) -> "EmbeddingStore":
        if self._embedding_store is None:
            from openrecall.server.database.embedding_store import EmbeddingStore
            self._embedding_store = EmbeddingStore()
        return self._embedding_store

    @property
    def provider(self) -> MultimodalEmbeddingProvider:
        if self._provider is None:
            from openrecall.server.ai.factory import get_multimodal_embedding_provider
            self._provider = get_multimodal_embedding_provider()
        return self._provider

    def enqueue_embedding_task(self, conn, frame_id: int) -> None:
        """Insert a pending embedding task for a frame. Idempotent."""
        try:
            conn.execute(
                """
                INSERT INTO embedding_tasks (frame_id, status)
                VALUES (?, 'pending')
                """,
                (frame_id,),
            )
            conn.execute(
                """
                UPDATE frames SET embedding_status = 'pending'
                WHERE id = ? AND embedding_status IS NULL
                """,
                (frame_id,),
            )
            conn.commit()
            logger.debug(f"Embedding task enqueued for frame #{frame_id}")
        except Exception as e:
            # Likely duplicate - ignore
            logger.debug(f"Failed to enqueue embedding task: {e}")

    def generate_embedding(
        self,
        image_path: str,
        text: Optional[str] = None,
    ) -> FrameEmbedding:
        """Call the embedding provider to generate an embedding."""
        vector = self.provider.embed_image(image_path, text)
        return FrameEmbedding(
            frame_id=0,  # Will be set by caller
            embedding_vector=vector.tolist(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def save_embedding(
        self,
        conn,
        frame_id: int,
        embedding: FrameEmbedding,
        timestamp: str,
        app_name: str = "",
        window_name: str = "",
    ) -> None:
        """Save embedding to LanceDB."""
        embedding.frame_id = frame_id
        embedding.timestamp = timestamp
        embedding.app_name = app_name
        embedding.window_name = window_name
        self.embedding_store.save_embedding(embedding)

    def mark_completed(self, conn, task_id: int, frame_id: int) -> None:
        """Mark an embedding task as completed."""
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE embedding_tasks
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (now, task_id),
        )
        conn.execute(
            """
            UPDATE frames SET embedding_status = 'completed'
            WHERE id = ?
            """,
            (frame_id,),
        )
        conn.commit()

    def mark_failed(
        self,
        conn,
        task_id: int,
        frame_id: int,
        error_message: str,
        retry_count: int,
    ) -> None:
        """Mark an embedding task as failed or schedule retry."""
        if retry_count < _MAX_RETRIES:
            delay_seconds = _RETRY_DELAYS[retry_count - 1]
            next_retry = datetime.now(timezone.utc).replace(microsecond=0)
            next_retry = next_retry + timedelta(seconds=delay_seconds)
            conn.execute(
                """
                UPDATE embedding_tasks
                SET retry_count = ?, next_retry_at = ?, error_message = ?
                WHERE id = ?
                """,
                (retry_count + 1, next_retry.isoformat(), error_message, task_id),
            )
            logger.info(
                f"Embedding task #{task_id} failed (retry {retry_count}/{_MAX_RETRIES}), "
                f"rescheduled at {next_retry.isoformat()}"
            )
        else:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE embedding_tasks
                SET status = 'failed', error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (error_message, now, task_id),
            )
            conn.execute(
                """
                UPDATE frames SET embedding_status = 'failed'
                WHERE id = ?
                """,
                (frame_id,),
            )
            logger.warning(
                f"Embedding task #{task_id} permanently failed after {_MAX_RETRIES} retries"
            )
        conn.commit()

    def get_queue_status(self, conn) -> dict[str, int]:
        """Return queue statistics."""
        rows = conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM embedding_tasks
            GROUP BY status
            """
        ).fetchall()
        result = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        for row in rows:
            status = row[0]
            count = row[1]
            if status in result:
                result[status] = count
        return result

    def backfill(self, conn) -> int:
        """Enqueue all frames without embedding_status. Returns count."""
        cursor = conn.execute(
            """
            INSERT INTO embedding_tasks (frame_id, status)
            SELECT id, 'pending' FROM frames
            WHERE embedding_status IS NULL
              AND id NOT IN (SELECT frame_id FROM embedding_tasks)
            """
        )
        conn.commit()
        return cursor.rowcount
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_embedding_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/embedding/service.py
git add tests/test_embedding_service.py
git commit -m "feat(embedding): add EmbeddingService for task management"
```

---

## Task 7: Embedding Worker

**Files:**
- Create: `openrecall/server/embedding/worker.py`
- Create: `tests/test_embedding_worker.py`

- [ ] **Step 1: Write failing test for EmbeddingWorker**

```python
# tests/test_embedding_worker.py
"""Tests for embedding worker."""
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from openrecall.server.embedding.worker import EmbeddingWorker


class TestEmbeddingWorker:
    def test_worker_processes_pending_task(self, tmp_path):
        """Worker should process pending task and mark completed."""
        # Create test database
        db_path = tmp_path / "test.db"
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        # Create a dummy image file
        test_image = frames_dir / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                snapshot_path TEXT,
                full_text TEXT,
                timestamp TEXT,
                app_name TEXT,
                window_name TEXT,
                embedding_status TEXT DEFAULT NULL
            );
            CREATE TABLE embedding_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(frame_id)
            );
        """)
        conn.execute(
            "INSERT INTO frames (id, snapshot_path, full_text, timestamp) VALUES (?, ?, ?, ?)",
            (1, str(test_image), "test text", "2026-04-09T12:00:00Z"),
        )
        conn.execute("INSERT INTO embedding_tasks (frame_id, status) VALUES (1, 'pending')")
        conn.commit()

        # Create mock store and service
        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)
        store._frames_dir = frames_dir

        # Create worker with mock provider
        mock_provider = Mock()
        mock_provider.embed_image.return_value = __import__("numpy").array([0.1] * 1024)

        worker = EmbeddingWorker(store=store, poll_interval=0.1)
        worker._provider = mock_provider

        # Run one iteration
        with conn:
            worker._process_batch(conn)

        # Verify task was completed
        task = conn.execute(
            "SELECT status FROM embedding_tasks WHERE frame_id = 1"
        ).fetchone()
        assert task[0] == "completed"

        # Verify frame status was updated
        frame = conn.execute(
            "SELECT embedding_status FROM frames WHERE id = 1"
        ).fetchone()
        assert frame[0] == "completed"

        conn.close()

    def test_worker_retries_on_failure(self, tmp_path):
        """Worker should retry failed tasks with exponential backoff."""
        db_path = tmp_path / "test.db"
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        test_image = frames_dir / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                snapshot_path TEXT,
                full_text TEXT,
                timestamp TEXT,
                embedding_status TEXT DEFAULT NULL
            );
            CREATE TABLE embedding_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(frame_id)
            );
        """)
        conn.execute(
            "INSERT INTO frames (id, snapshot_path, full_text, timestamp) VALUES (?, ?, ?, ?)",
            (1, str(test_image), "test", "2026-04-09T12:00:00Z"),
        )
        conn.execute("INSERT INTO embedding_tasks (frame_id, status) VALUES (1, 'pending')")
        conn.commit()

        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)

        # Create worker with failing provider
        mock_provider = Mock()
        mock_provider.embed_image.side_effect = Exception("API error")

        worker = EmbeddingWorker(store=store)
        worker._provider = mock_provider

        with conn:
            worker._process_batch(conn)

        # Verify task was rescheduled
        task = conn.execute(
            "SELECT retry_count, next_retry_at FROM embedding_tasks WHERE frame_id = 1"
        ).fetchone()
        assert task[0] == 1  # retry_count incremented
        assert task[1] is not None  # next_retry_at set

        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embedding_worker.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement EmbeddingWorker**

```python
# openrecall/server/embedding/worker.py
"""Background worker for frame embedding generation."""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from openrecall.server.database.frames_store import FramesStore

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2.0  # seconds
_STATS_INTERVAL = 60.0  # seconds


class EmbeddingWorker(threading.Thread):
    """Background worker thread that processes pending embedding tasks."""

    def __init__(
        self,
        store: "FramesStore",
        poll_interval: float = _POLL_INTERVAL,
    ):
        super().__init__(daemon=True, name="EmbeddingWorker")
        self._store = store
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._service = None
        self._last_stats_time = 0.0

    @property
    def service(self):
        if self._service is None:
            from openrecall.server.embedding.service import EmbeddingService
            self._service = EmbeddingService(store=self._store)
        return self._service

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("EmbeddingWorker started")
        while not self._stop_event.is_set():
            try:
                with self._store._connect() as conn:
                    self._process_batch(conn)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    logger.warning("Database locked, will retry")
                else:
                    logger.error(f"Database error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}")
            self._stop_event.wait(timeout=self._poll_interval)
        logger.info("EmbeddingWorker stopped")

    def _log_queue_status(self, conn: sqlite3.Connection) -> None:
        """Log queue statistics periodically."""
        now = time.time()
        if now - self._last_stats_time >= _STATS_INTERVAL:
            try:
                status = self.service.get_queue_status(conn)
                logger.info(
                    f"Embedding queue stats: pending={status.get('pending', 0)}, "
                    f"processing={status.get('processing', 0)}, "
                    f"failed={status.get('failed', 0)}"
                )
            except Exception as e:
                logger.debug(f"Failed to get queue status: {e}")
            self._last_stats_time = now

    def _process_batch(self, conn: sqlite3.Connection) -> None:
        """Fetch and process one pending embedding task."""
        self._log_queue_status(conn)

        task = self._store.claim_embedding_task(conn)
        if task is None:
            logger.debug("No pending embedding tasks")
            return

        task_id, frame_id = task["id"], task["frame_id"]
        logger.debug(f"Processing embedding task #{task_id} for frame #{frame_id}")

        frame = self._store.get_frame_by_id(frame_id, conn)
        if frame is None:
            logger.warning(f"Frame #{frame_id} not found, skipping task #{task_id}")
            return

        snapshot_path = frame.get("snapshot_path")
        if not snapshot_path:
            logger.warning(f"Frame #{frame_id} has no snapshot_path, skipping")
            self.service.mark_failed(conn, task_id, frame_id, "No snapshot_path", 1)
            return

        try:
            embedding = self.service.generate_embedding(
                image_path=snapshot_path,
                text=frame.get("full_text"),
            )
            self.service.save_embedding(
                conn,
                frame_id,
                embedding,
                timestamp=frame.get("timestamp", ""),
                app_name=frame.get("app_name", ""),
                window_name=frame.get("window_name", ""),
            )
            self.service.mark_completed(conn, task_id, frame_id)
            logger.info(f"Embedding completed for frame #{frame_id}")
        except Exception as e:
            logger.error(f"Embedding generation failed for frame #{frame_id}: {e}")
            retry_count = task.get("retry_count", 0) + 1
            self.service.mark_failed(conn, task_id, frame_id, str(e), retry_count)
```

- [ ] **Step 4: Add claim_embedding_task to FramesStore**

```python
# Add to openrecall/server/database/frames_store.py

def claim_embedding_task(
    self,
    conn: sqlite3.Connection,
) -> Optional[dict]:
    """Atomically claim the next pending embedding task. Returns dict or None."""
    cursor = conn.execute(
        """
        WITH next_task AS (
            SELECT id FROM embedding_tasks
            WHERE status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ORDER BY created_at ASC
            LIMIT 1
        )
        UPDATE embedding_tasks
        SET status = 'processing', started_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = (SELECT id FROM next_task)
        RETURNING id, frame_id, retry_count
        """
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "frame_id": row[1],
        "retry_count": row[2],
    }

def get_frames_by_ids(
    self,
    frame_ids: List[int],
) -> Dict[int, dict]:
    """Fetch multiple frames by ID. Returns dict mapping frame_id to frame data."""
    if not frame_ids:
        return {}

    placeholders = ",".join("?" * len(frame_ids))
    with self._connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, timestamp, full_text, app_name, window_name,
                   browser_url, focused, device_name, snapshot_path
            FROM frames
            WHERE id IN ({placeholders})
            """,
            frame_ids,
        ).fetchall()

    result = {}
    for row in rows:
        frame_id = row[0]
        result[frame_id] = {
            "frame_id": frame_id,
            "timestamp": row[1],
            "full_text": row[2],
            "app_name": row[3] or "",
            "window_name": row[4] or "",
            "browser_url": row[5],
            "focused": row[6],
            "device_name": row[7] or "monitor_0",
            "snapshot_path": row[8],
        }
    return result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_embedding_worker.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/embedding/worker.py
git add openrecall/server/database/frames_store.py
git add tests/test_embedding_worker.py
git commit -m "feat(embedding): add EmbeddingWorker for background processing"
```

---

## Task 7b: Worker Startup Integration

**Files:**
- Modify: `openrecall/server/__main__.py`

- [ ] **Step 1: Add EmbeddingWorker startup in OCR mode**

Find the `_start_ocr_mode()` function in `openrecall/server/__main__.py`. After the DescriptionWorker startup block, add similar code for EmbeddingWorker:

```python
# In _start_ocr_mode(), after DescriptionWorker startup:
if settings.embedding_enabled:
    from openrecall.server.embedding.worker import EmbeddingWorker
    _embedding_worker = EmbeddingWorker(store)
    _embedding_worker.start()
    logger.info("EmbeddingWorker started (ocr mode)")
```

- [ ] **Step 2: Verify worker startup order**

The startup order should be:
1. DescriptionWorker (if description_enabled)
2. EmbeddingWorker (if embedding_enabled)

Both run parallel - no dependency between them.

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/__main__.py
git commit -m "feat(server): add EmbeddingWorker startup in OCR mode"
```

---

## Task 8: Hybrid Search Engine

**Files:**
- Create: `openrecall/server/search/hybrid_engine.py`
- Create: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write failing test for RRF fusion**

```python
# tests/test_hybrid_search.py
"""Tests for hybrid search (FTS + vector)."""
import pytest

from openrecall.server.search.hybrid_engine import (
    reciprocal_rank_fusion,
    HybridSearchEngine,
)


class TestReciprocalRankFusion:
    def test_rrf_merges_results(self):
        """RRF should merge FTS and vector results."""
        fts_results = [
            {"frame_id": 1, "text": "result 1"},
            {"frame_id": 2, "text": "result 2"},
            {"frame_id": 3, "text": "result 3"},
        ]
        vector_results = [
            {"frame_id": 3, "similarity": 0.95},
            {"frame_id": 1, "similarity": 0.90},
            {"frame_id": 4, "similarity": 0.85},
        ]

        merged = reciprocal_rank_fusion(
            fts_results=fts_results,
            vector_results=vector_results,
        )

        # Frame 1 and 3 appear in both - should rank higher
        frame_ids = [m[0] for m in merged]
        assert 1 in frame_ids
        assert 3 in frame_ids
        # Frame 1 and 3 should be in top positions
        assert frame_ids[0] in [1, 3]

    def test_rrf_empty_inputs(self):
        """RRF should handle empty inputs."""
        result = reciprocal_rank_fusion([], [])
        assert result == []

        result = reciprocal_rank_fusion([{"frame_id": 1}], [])
        assert result == [(1, pytest.approx(0.5 / 61, rel=0.01))]

    def test_rrf_weights(self):
        """RRF should respect weight parameters."""
        fts_results = [{"frame_id": 1}]
        vector_results = [{"frame_id": 2}]

        # Higher FTS weight should favor FTS result
        merged_fts = reciprocal_rank_fusion(
            fts_results, vector_results, fts_weight=0.9, vector_weight=0.1
        )
        merged_vec = reciprocal_rank_fusion(
            fts_results, vector_results, fts_weight=0.1, vector_weight=0.9
        )

        # Frame 1 score should be higher in fts_weighted
        fts_score_1 = next(s for f, s in merged_fts if f == 1)
        vec_score_1 = next(s for f, s in merged_vec if f == 1)
        assert fts_score_1 > vec_score_1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hybrid_search.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement hybrid engine**

```python
# openrecall/server/search/hybrid_engine.py
"""Hybrid search engine combining FTS5 and vector search."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    fts_results: List[Dict[str, Any]],
    vector_results: List[Dict[str, Any]],
    k: int = 60,
    fts_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> List[Tuple[int, float]]:
    """Merge FTS and vector search results using RRF.

    RRF formula: score = weight / (k + rank)

    Args:
        fts_results: FTS search results with 'frame_id' key
        vector_results: Vector search results with 'frame_id' key
        k: RRF smoothing parameter (default 60)
        fts_weight: Weight for FTS results (default 0.5)
        vector_weight: Weight for vector results (default 0.5)

    Returns:
        List of (frame_id, score) tuples sorted by score descending
    """
    scores = defaultdict(float)

    # Process FTS results
    for rank, result in enumerate(fts_results, start=1):
        frame_id = result.get("frame_id")
        if frame_id is not None:
            scores[frame_id] += fts_weight / (k + rank)

    # Process vector results
    for rank, result in enumerate(vector_results, start=1):
        frame_id = result.get("frame_id")
        if frame_id is not None:
            scores[frame_id] += vector_weight / (k + rank)

    # Sort by score descending
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridSearchEngine:
    """Hybrid search combining FTS5 and vector similarity."""

    def __init__(self):
        from openrecall.server.search.engine import SearchEngine
        from openrecall.server.database.embedding_store import EmbeddingStore

        self._fts_engine = SearchEngine()
        self._embedding_store = EmbeddingStore()

    def search(
        self,
        q: str = "",
        mode: str = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Execute hybrid search.

        Args:
            q: Text query
            mode: 'fts', 'vector', or 'hybrid' (default)
            fts_weight: Weight for FTS results in hybrid mode
            vector_weight: Weight for vector results in hybrid mode
            limit: Max results
            offset: Pagination offset
            **kwargs: Additional filters passed to FTS engine

        Returns:
            Tuple of (results list, total count)
        """
        mode = mode.lower().strip()
        if mode not in ("fts", "vector", "hybrid"):
            mode = "hybrid"

        if mode == "fts":
            return self._fts_only_search(q, limit, offset, **kwargs)
        elif mode == "vector":
            return self._vector_only_search(q, limit, offset)
        else:
            return self._hybrid_search(
                q, fts_weight, vector_weight, limit, offset, **kwargs
            )

    def _fts_only_search(
        self, q: str, limit: int, offset: int, **kwargs
    ) -> Tuple[List[Dict[str, Any]], int]:
        """FTS-only search."""
        return self._fts_engine.search(q=q, limit=limit, offset=offset, **kwargs)

    def _vector_only_search(
        self, q: str, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Vector-only search."""
        if not q or q.isspace():
            return [], 0

        # Get query embedding
        from openrecall.server.ai.factory import get_multimodal_embedding_provider
        provider = get_multimodal_embedding_provider()
        query_vector = provider.embed_text(q)

        # Search embeddings
        embeddings = self._embedding_store.search(
            query_vector.tolist(), limit=limit + offset
        )

        results = []
        for emb in embeddings[offset : offset + limit]:
            results.append({
                "frame_id": emb.frame_id,
                "timestamp": emb.timestamp,
                "text": "",  # Will need to fetch from frames if needed
                "app_name": emb.app_name,
                "window_name": emb.window_name,
                "browser_url": None,
                "focused": None,
                "device_name": "monitor_0",
                "file_path": f"{emb.timestamp}.jpg",
                "frame_url": f"/v1/frames/{emb.frame_id}",
                "tags": [],
            })

        return results, len(embeddings)

    def _hybrid_search(
        self,
        q: str,
        fts_weight: float,
        vector_weight: float,
        limit: int,
        offset: int,
        **kwargs,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Hybrid search with RRF fusion."""
        # Run both searches in parallel (for now, sequentially)
        fts_results, _ = self._fts_engine.search(q=q, limit=limit * 2, **kwargs)

        vector_results = []
        if q and not q.isspace():
            from openrecall.server.ai.factory import get_multimodal_embedding_provider
            provider = get_multimodal_embedding_provider()
            query_vector = provider.embed_text(q)
            embeddings = self._embedding_store.search(
                query_vector.tolist(), limit=limit * 2
            )
            vector_results = [
                {"frame_id": e.frame_id, "similarity": 1.0} for e in embeddings
            ]

        # Merge with RRF
        merged = reciprocal_rank_fusion(
            fts_results, vector_results, fts_weight=fts_weight, vector_weight=vector_weight
        )

        # Apply pagination
        total = len(merged)
        merged = merged[offset : offset + limit]

        # Build final results - fetch full frame data from database
        frame_ids = [frame_id for frame_id, score in merged]
        scores = {frame_id: score for frame_id, score in merged}

        # Fetch full frame data from frames table
        from openrecall.server.database.frames_store import FramesStore
        frames_store = FramesStore()
        frame_data_map = frames_store.get_frames_by_ids(frame_ids)

        results = []
        for frame_id in frame_ids:
            frame = frame_data_map.get(frame_id, {})
            results.append({
                "frame_id": frame_id,
                "hybrid_score": scores.get(frame_id, 0.0),
                "timestamp": frame.get("timestamp", ""),
                "text": frame.get("full_text", "")[:200] if frame.get("full_text") else "",
                "app_name": frame.get("app_name", ""),
                "window_name": frame.get("window_name", ""),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "file_path": frame.get("file_path", f"{frame.get('timestamp', '')}.jpg"),
                "frame_url": f"/v1/frames/{frame_id}",
                "tags": [],
            })

        return results, total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hybrid_search.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/search/hybrid_engine.py
git add tests/test_hybrid_search.py
git commit -m "feat(search): add hybrid search engine with RRF fusion"
```

---

## Task 9: Factory Integration

**Files:**
- Modify: `openrecall/server/ai/factory.py`
- Modify: `openrecall/shared/config.py` (add embedding config fields)

- [ ] **Step 1: Add embedding config to settings**

Add to `openrecall/shared/config.py` after the description config fields:

```python
# Embedding Settings (multimodal)
embedding_enabled: bool = Field(
    default=True,
    alias="OPENRECALL_EMBEDDING_ENABLED",
    description="Enable embedding generation for frames",
)
embedding_provider: str = Field(
    default="openai",
    alias="OPENRECALL_EMBEDDING_PROVIDER",
    description="Embedding provider: openai, dashscope",
)
embedding_model: str = Field(
    default="qwen3-vl-embedding",
    alias="OPENRECALL_EMBEDDING_MODEL",
    description="Embedding model name",
)
embedding_api_key: str = Field(
    default="",
    alias="OPENRECALL_EMBEDDING_API_KEY",
    description="API key for embedding provider",
)
embedding_api_base: str = Field(
    default="",
    alias="OPENRECALL_EMBEDDING_API_BASE",
    description="API base URL for embedding provider",
)
embedding_dim: int = Field(
    default=1024,
    alias="OPENRECALL_EMBEDDING_DIM",
    description="Embedding vector dimension",
)
```

- [ ] **Step 2: Add get_multimodal_embedding_provider to factory**

Add to `openrecall/server/ai/factory.py`:

```python
def get_multimodal_embedding_provider() -> "MultimodalEmbeddingProvider":
    """Get or create a cached MultimodalEmbeddingProvider instance."""
    from openrecall.server.embedding.providers import (
        MultimodalEmbeddingProvider,
        OpenAIMultimodalEmbeddingProvider,
    )

    capability = "multimodal_embedding"
    cached = _instances.get(capability)
    if cached is not None:
        return cached  # type: ignore[return-value]

    provider = settings.embedding_provider.strip().lower() if settings.embedding_provider else "openai"
    model_name = settings.embedding_model
    api_key = settings.embedding_api_key
    api_base = settings.embedding_api_base

    if provider == "openai":
        instance: MultimodalEmbeddingProvider = OpenAIMultimodalEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    else:
        raise AIProviderConfigError(f"Unknown embedding provider: {provider}")

    _instances[capability] = instance
    return instance
```

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `pytest tests/test_description_provider.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/ai/factory.py
git add openrecall/shared/config.py
git commit -m "feat(config): add embedding provider configuration"
```

---

## Task 10: API Endpoints

**Files:**
- Modify: `openrecall/server/api_v1.py`

- [ ] **Step 1: Add embedding task creation to ingest flow (parallel to description_task)**

In `openrecall/server/api_v1.py`, find where `insert_description_task` is called after frame creation. Add embedding task creation in parallel:

```python
# In ingest endpoint, after frame is successfully created:
# Step 6: Enqueue description task if enabled (EXISTING CODE)
if settings.description_enabled:
    try:
        with store._connect() as conn:
            store.insert_description_task(conn, frame_id)
            conn.commit()
            logger.debug(
                "ingest: description task enqueued capture_id=%s frame_id=%d",
                capture_id_raw,
                frame_id,
            )
    except Exception as e:
        logger.warning(
            "ingest: failed to enqueue description task capture_id=%s frame_id=%d: %s",
            capture_id_raw,
            frame_id,
            e,
        )

# Step 7: Enqueue embedding task if enabled (NEW CODE - PARALLEL)
if settings.embedding_enabled:
    try:
        with store._connect() as conn:
            store.insert_embedding_task(conn, frame_id)
            conn.commit()
            logger.debug(
                "ingest: embedding task enqueued capture_id=%s frame_id=%d",
                capture_id_raw,
                frame_id,
            )
    except Exception as e:
        logger.warning(
            "ingest: failed to enqueue embedding task capture_id=%s frame_id=%d: %s",
            capture_id_raw,
            frame_id,
            e,
        )
```

Add `insert_embedding_task` method to FramesStore:

```python
def insert_embedding_task(self, conn: sqlite3.Connection, frame_id: int) -> None:
    """Insert a pending embedding task for a frame. Idempotent."""
    try:
        conn.execute(
            """
            INSERT INTO embedding_tasks (frame_id, status)
            VALUES (?, 'pending')
            """,
            (frame_id,),
        )
        conn.execute(
            """
            UPDATE frames SET embedding_status = 'pending'
            WHERE id = ? AND embedding_status IS NULL
            """,
            (frame_id,),
        )
    except sqlite3.IntegrityError:
        # Task already exists - ignore
        pass
```

- [ ] **Step 2: Add GET /v1/embedding/tasks/status endpoint**

```python
@v1_bp.route("/embedding/tasks/status", methods=["GET"])
def embedding_tasks_status():
    """Return embedding task queue statistics."""
    from openrecall.server.embedding.service import EmbeddingService
    from openrecall.server.database.frames_store import FramesStore

    store = FramesStore()
    service = EmbeddingService(store=store)

    with store._connect() as conn:
        status = service.get_queue_status(conn)

    return jsonify(status)
```

- [ ] **Step 3: Add GET /v1/frames/<frame_id>/similar endpoint**

```python
@v1_bp.route("/frames/<int:frame_id>/similar", methods=["GET"])
def similar_frames(frame_id: int):
    """Find similar frames using vector similarity."""
    from openrecall.server.database.embedding_store import EmbeddingStore
    from openrecall.server.database.frames_store import FramesStore
    import numpy as np

    limit = request.args.get("limit", 10, type=int)
    limit = max(1, min(limit, 100))

    store = EmbeddingStore()
    frames_store = FramesStore()

    # Get the frame's embedding
    embedding = store.get_by_frame_id(frame_id)
    if embedding is None:
        return jsonify({"error": "Embedding not found for frame"}), 404

    # Search for similar frames
    # Returns (frame_id, distance) tuples from LanceDB
    results_with_distance = store.search_with_distance(
        embedding.embedding_vector, limit=limit + 1
    )

    # Filter out the query frame itself and calculate similarity
    # LanceDB returns cosine distance, similarity = 1 - distance
    similar = []
    for r, distance in results_with_distance:
        if r.frame_id != frame_id:
            similarity = max(0.0, 1.0 - float(distance))
            similar.append({
                "frame_id": r.frame_id,
                "similarity": round(similarity, 4),
                "timestamp": r.timestamp,
                "app_name": r.app_name,
                "window_name": r.window_name,
                "frame_url": f"/v1/frames/{r.frame_id}",
            })
        if len(similar) >= limit:
            break

    return jsonify({
        "frame_id": frame_id,
        "similar_frames": similar,
    })
```

**Note:** Requires adding `search_with_distance()` method to EmbeddingStore that returns distance along with results.

- [ ] **Step 4: Extend /v1/search to support mode parameter**

Modify the search endpoint to accept `mode` parameter and use HybridSearchEngine when mode != 'fts':

```python
# In search() function, add:
mode = request.args.get("mode", "fts").strip().lower()
if mode not in ("fts", "vector", "hybrid"):
    mode = "fts"

fts_weight = request.args.get("fts_weight", 0.5, type=float)
vector_weight = request.args.get("vector_weight", 0.5, type=float)

# Clamp weights
fts_weight = max(0.0, min(1.0, fts_weight))
vector_weight = max(0.0, min(1.0, vector_weight))

if mode != "fts":
    from openrecall.server.search.hybrid_engine import HybridSearchEngine
    hybrid_engine = HybridSearchEngine()
    results, total = hybrid_engine.search(
        q=q,
        mode=mode,
        fts_weight=fts_weight,
        vector_weight=vector_weight,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
        window_name=window_name,
    )
    # ... continue with existing response format
```

- [ ] **Step 5: Run API tests**

Run: `pytest tests/test_embedding_api.py -v`
Expected: PASS (create basic API tests if needed)

- [ ] **Step 6: Commit**

```bash
git add openrecall/server/api_v1.py
git commit -m "feat(api): add embedding endpoints and hybrid search support"
```

---

## Task 11: Update Module Exports

**Files:**
- Modify: `openrecall/server/embedding/__init__.py`

- [ ] **Step 1: Update module exports**

```python
# openrecall/server/embedding/__init__.py
"""Frame embedding module for multimodal vector search."""
from openrecall.server.embedding.models import FrameEmbedding
from openrecall.server.embedding.service import EmbeddingService
from openrecall.server.embedding.worker import EmbeddingWorker

__all__ = [
    "FrameEmbedding",
    "EmbeddingService",
    "EmbeddingWorker",
]
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/server/embedding/__init__.py
git commit -m "chore(embedding): update module exports"
```

---

## Task 12: Configuration Documentation

**Files:**
- Modify: `myrecall_server.toml.example`

- [ ] **Step 1: Add embedding configuration section**

Add to `myrecall_server.toml.example` after the description section:

```toml
# ==============================================================================
# Embedding Settings (Multimodal Vector Search)
# ==============================================================================
# IMPORTANT: [embedding] section is INDEPENDENT from [ai] section.
# Configure explicitly for embedding generation.
#
# For qwen3-vl-embedding via DashScope:
#   [embedding]
#   enabled = true
#   provider = "openai"
#   model = "text-embedding-v3"
#   api_key = "sk-..."
#   api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
#
# For local vLLM service:
#   [embedding]
#   enabled = true
#   provider = "openai"
#   model = "qwen3-vl-embedding"
#   api_base = "http://localhost:8000/v1"
# ==============================================================================
[embedding]
enabled = true                      # Enable embedding generation
provider = "openai"                 # Options: openai
model = "qwen3-vl-embedding"        # Embedding model name
api_key = ""                        # API key if required
api_base = ""                       # API base URL (e.g., http://localhost:8000/v1)
dim = 1024                          # Embedding dimension
```

- [ ] **Step 2: Commit**

```bash
git add myrecall_server.toml.example
git commit -m "docs(config): add embedding configuration section"
```

---

## Task 13: Integration Tests

**Files:**
- Create: `tests/test_embedding_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_embedding_integration.py
"""Integration tests for embedding feature."""
import pytest


@pytest.mark.integration
class TestEmbeddingIntegration:
    def test_full_flow(self, tmp_path):
        """Test full embedding flow from task creation to search."""
        # This test requires a running server with embedding provider configured
        # Skip if not available
        pytest.skip("Integration test - requires running server")

    def test_backfill_endpoint(self):
        """Test embedding backfill for historical frames."""
        pytest.skip("Integration test - requires running server")

    def test_hybrid_search_returns_results(self):
        """Test hybrid search returns combined results."""
        pytest.skip("Integration test - requires running server")
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_embedding_integration.py
git commit -m "test(embedding): add integration test stubs"
```

---

## Task 14: Final Verification

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v --ignore=tests/archive`
Expected: All tests pass

- [ ] **Step 2: Run linting**

Run: `ruff check openrecall/`
Expected: No errors (or fix any issues)

- [ ] **Step 3: Create summary commit**

```bash
git add -A
git commit -m "feat(embedding): complete multimodal embedding implementation

- Add FrameEmbedding model and LanceDB store
- Add OpenAI-compatible multimodal embedding provider
- Add EmbeddingWorker for background processing
- Add hybrid search with RRF fusion
- Add API endpoints: /embedding/tasks/status, /frames/{id}/similar
- Extend /v1/search with mode parameter for hybrid search"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Database migration | 1 new |
| 2 | Embedding models | 2 new, 1 test |
| 3 | Provider protocol | 2 new, 1 test |
| 4 | OpenAI provider | 1 new, 1 modify, 1 test |
| 5 | Embedding store (with search_with_distance) | 1 new, 1 test |
| 6 | Embedding service | 1 new, 1 test |
| 7 | Embedding worker | 1 new, 1 test |
| 7b | Worker startup integration | 1 modify |
| 8 | Hybrid search engine (with full frame data) | 1 new, 1 test |
| 9 | Factory integration | 2 modify |
| 10 | API endpoints (ingest trigger + similar with score) | 1 modify |
| 11 | Module exports | 1 modify |
| 12 | Config documentation | 1 modify |
| 13 | Integration tests | 1 new |
| 14 | Final verification | - |
