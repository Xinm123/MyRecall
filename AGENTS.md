# AGENTS.md - OpenRecall Development Guide

## Project Overview

OpenRecall is a privacy-first digital memory application that captures screenshots, extracts text via OCR, and provides semantic search. Architecture: Flask server + Python client with local AI processing.

## Build/Lint/Test Commands

```bash
# Install (development mode with test dependencies)
pip install -e ".[test]"

# Run all tests (excluding e2e, perf, security, model, manual)
pytest

# Run a single test file
pytest tests/test_nlp.py

# Run a single test function
pytest tests/test_nlp.py::test_cosine_similarity_identical_vectors

# Run tests with specific markers
pytest -m "unit"           # Unit tests only
pytest -m "integration"    # Integration tests only
pytest -m "model"          # Model/AI tests (requires GPU/models)
pytest -m "security"       # Security tests
pytest -m "perf"           # Performance benchmarks
pytest -m "e2e"            # End-to-end tests

# Run with coverage
pytest --cov=openrecall --cov-report=html 

# Run server
./run_server.sh

# Run client
./run_client.sh
```

## Code Style Guidelines

### Import Organization

Three groups separated by blank lines: stdlib, third-party, local (alphabetical within each).

```python
# 1. Standard library
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

# 2. Third-party
import numpy as np
from flask import Blueprint, jsonify, request
from pydantic import BaseModel, Field

# 3. Local imports (absolute, never relative)
from openrecall.server.database import SQLStore
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)
```

Use `from __future__ import annotations` for forward references when needed.

### Type Hints

Comprehensive type annotations on all functions and class attributes. Use modern union syntax.

```python
# Function signatures - always include return type
def search(self, query: str, limit: int = 50) -> List[SemanticSnapshot]:
    ...

# Modern union syntax (X | None, not Optional[X])
class RecallEntry(BaseModel):
    id: int | None = None
    timestamp: int
    text: str | None = None
    embedding: Any | None = None

# Tuple returns
def _resolve_config() -> tuple[str, str, str, str]:
    return provider, model, key, base
```

### Docstrings (Google Style)

```python
def upload():
    """Fast screenshot ingestion endpoint (Fire-and-Forget).
    
    Accepts multipart/form-data:
    - file: Image file (PNG)
    - metadata: JSON string with timestamp, app_name, window_title
    
    Returns:
        HTTP 202 Accepted with task ID.
    """

class LocalBuffer:
    """Thread-safe, file-system-backed queue for screenshot buffering.
    
    Uses atomic write pattern (.tmp -> rename) to ensure data integrity.
    
    Attributes:
        storage_dir: Directory for storing buffered files.
    """
```

For Pydantic models, use Field descriptions:

```python
class Content(BaseModel):
    ocr_text: str = Field(description="Full text extracted via OCR for FTS")
    caption: str = Field(description="Natural language description of the scene")
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Classes | PascalCase | `ProcessingWorker`, `SQLStore`, `AIProvider` |
| Functions | snake_case | `search_api()`, `get_memories_since()` |
| Variables | snake_case | `user_query`, `results_map`, `timestamp` |
| Constants | UPPER_SNAKE | `MAX_IMAGE_SIZE`, `MODEL_ID` |
| Private | underscore prefix | `_init_db()`, `_FallbackProvider` |

### Error Handling

Custom exception hierarchy in `openrecall/server/ai/base.py`:

```python
class AIProviderError(Exception):
    pass

class AIProviderConfigError(AIProviderError):
    pass

class AIProviderUnavailableError(AIProviderError):
    pass
```

Error handling patterns:

```python
# Graceful fallback
try:
    ai_provider = get_ai_provider()
except Exception as e:
    logger.error(f"Failed to initialize provider: {e}")
    ai_provider = _FallbackProvider()

# API error responses
try:
    results = search_engine.search(q, limit=limit)
except Exception as e:
    logger.exception("Search error")  # Full traceback
    return jsonify({"status": "error", "message": str(e)}), 500
```

## Testing Conventions

### Test File Structure

- Location: `tests/`
- Naming: `test_<module>.py`
- Config: `pytest.ini`, `tests/conftest.py`

### Test Function Naming

Pattern: `test_<action>_<scenario>_<expected>`

```python
def test_nlp_engine_encode_empty_text_returns_zero():
    ...

def test_update_config_rejects_unknown_field():
    ...
```

### Fixtures (conftest.py)

```python
@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    """Flask app with isolated temp directory."""
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    importlib.reload(openrecall.shared.config)
    return openrecall.server.app.app

@pytest.fixture
def flask_client(flask_app):
    """Test client for API calls."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
```

### Pytest Markers

Defined in `pytest.ini`:

```python
@pytest.mark.unit        # Unit tests
@pytest.mark.integration # Integration tests
@pytest.mark.e2e         # End-to-end tests
@pytest.mark.model       # Requires AI models
@pytest.mark.security    # Security tests
@pytest.mark.perf        # Performance benchmarks

# Module-level marker
pytestmark = pytest.mark.security

# Conditional skip
@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Skip in CI")
```

### Mocking Patterns

**Preferred: pytest monkeypatch**

```python
def test_nlp_engine_encode(monkeypatch):
    import openrecall.server.nlp as nlp
    
    class DummyModel:
        def encode(self, *args, **kwargs):
            return np.ones((8,), dtype=np.float32)
    
    monkeypatch.setattr(nlp, "SentenceTransformer", lambda *a, **k: DummyModel())
    monkeypatch.setattr(nlp.settings, "embedding_dim", 8)
    
    engine = nlp.NLPEngine()
    assert engine.encode("test").shape == (8,)
```

**Environment variables:**

```python
monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
```

### Unit vs Integration Tests

**Unit tests** - mock external dependencies:

```python
def test_cosine_similarity_identical_vectors():
    a = np.array([1, 0, 0])
    b = np.array([1, 0, 0])
    assert cosine_similarity(a, b) == 1.0
```

**Integration tests** - real DB/filesystem:

```python
class TestPhase2Ingestion(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        settings.screenshots_path.mkdir(parents=True, exist_ok=True)
    
    def test_upload_multipart(self):
        response = self.client.post('/api/upload', data={...})
        self.assertEqual(response.status_code, 202)
        # Verify DB entry exists
        with sqlite3.connect(str(settings.db_path)) as conn:
            ...
```

## Project Structure

```
openrecall/
  server/           # Flask API server
    api.py          # REST endpoints
    app.py          # Flask app factory
    worker.py       # Background processing thread
    ai/             # AI provider implementations
    database/       # SQLite + LanceDB stores
    search/         # Hybrid search engine
  client/           # Screenshot capture client
    recorder.py     # Screen capture
    uploader.py     # Server upload
    buffer.py       # Offline queue
  shared/           # Shared utilities
    config.py       # pydantic-settings configuration
    models.py       # Pydantic data models
tests/              # Test suite
```

## Configuration

Environment variables (see `openrecall/shared/config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENRECALL_DATA_DIR` | `~/.myrecall_data` | Data storage path |
| `OPENRECALL_PORT` | `8083` | Server port |
| `OPENRECALL_DEVICE` | `cpu` | AI inference device |
| `OPENRECALL_AI_PROVIDER` | `local` | Vision provider |
| `OPENRECALL_DEBUG` | `true` | Verbose logging |

## Key Patterns

### Singleton Pattern

```python
_engine: Optional[NLPEngine] = None

def get_nlp_engine() -> NLPEngine:
    global _engine
    if _engine is None:
        _engine = NLPEngine()
    return _engine
```

### Pydantic Settings

```python
class Settings(BaseSettings):
    debug: bool = Field(default=True, alias="OPENRECALL_DEBUG")
    port: int = Field(default=8083, alias="OPENRECALL_PORT")
    
    model_config = {
        "env_prefix": "",
        "populate_by_name": True,
        "env_file": ["openrecall.env", ".env"],
    }

settings = Settings()  # Global instance
```

### Thread-Safe Processing

```python
class ProcessingWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="ProcessingWorker")
        self._stop_event = threading.Event()
    
    def stop(self):
        self._stop_event.set()
    
    def run(self):
        while not self._stop_event.is_set():
            # Process tasks
            self._stop_event.wait(0.5)
```
