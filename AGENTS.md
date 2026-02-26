# OpenRecall Developer Guide

## Project Overview

OpenRecall is a privacy-first digital memory system that captures screenshots and uses local AI to make them searchable. The project has a client-server architecture with a Flask/FastAPI backend and Python client.

## Build, Test & Development Commands

### Running the Application

```bash
# Activate conda environment
conda activate old

# Run server (Terminal 1)
cd MyRecall
./run_server.sh --debug

# Run client (Terminal 2)
cd MyRecall
./run_client.sh --debug

```

### Testing

```bash
# Activate conda environment
conda activate old

# Run all tests (excludes e2e, perf, security, model, manual by default)
pytest

# Run a specific test file
pytest tests/test_phase5_buffer.py

# Run a specific test by name
pytest -k "test_enqueue_creates_files"

# Run tests with verbose output
pytest -v

# Run tests with coverage
pytest --cov=openrecall --cov-report=term-missing

# Run specific test markers
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not e2e"     # Exclude e2e tests

# Run all tests including slow ones (e2e, perf, security, model)
pytest --ignore-glob="*e2e*" -m ""

# Run a specific test in a class
pytest tests/test_phase5_buffer.py::TestLocalBuffer::test_enqueue_creates_files
```

### Linting & Code Quality

```bash
# Activate conda environment
conda activate old

# Run pytest with strict markers
pytest --strict-markers

# Coverage report (fails if below 80%)
pytest --cov=openrecall --cov-fail-under=80
```

## Code Style Guidelines

### Imports

Order imports in the following groups (separate each group with a blank line):

1. Standard library (`logging`, `time`, `pathlib`, `typing`, `tempfile`)
2. Third-party packages (`flask`, `numpy`, `pydantic`, `pytest`)
3. Local application imports (`openrecall.server`, `openrecall.shared`)

```python
# Correct import order
import logging
import time
from pathlib import Path
from typing import Optional, Union

import numpy as np
from flask import Blueprint, jsonify, request
from pydantic import Field, model_validator

from openrecall.server.database import SQLStore
from openrecall.shared.config import settings
```

### Type Hints

- Use type hints for all function signatures
- Use `Optional[T]` instead of `T | None` for Python 3.9 compatibility
- Use Python 3.9-style generic types (e.g., `list[str]`, `dict[str, int]`)

```python
# Good
def process_data(items: list[str]) -> dict[str, int]:
    """Process items and return counts."""
    result: dict[str, int] = {}
    return result

def find_item(items: list[str], key: str) -> Optional[str]:
    """Find item or return None."""
    for item in items:
        if item == key:
            return item
    return None
```

### Naming Conventions

- **Classes**: PascalCase (e.g., `SQLStore`, `SearchEngine`)
- **Functions/variables**: snake_case (e.g., `get_results()`, `image_path`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_RETRIES = 3`)
- **Private methods**: Prefix with underscore (e.g., `_internal_method()`)
- **Module names**: snake_case (e.g., `database.py`, `sql_store.py`)

### Docstrings

Use Google-style docstrings with Args, Returns, Raises sections:

```python
def search_api(q: str, limit: int = 50) -> list[dict]:
    """Hybrid Search Endpoint.
    
    Args:
        q: Search query string
        limit: Max results (default 50)
        
    Returns:
        JSON list of SemanticSnapshot objects.
        
    Raises:
        ValueError: If limit is negative
    """
```

### Error Handling

- Use `logger.exception()` for caught exceptions (logs stack trace)
- Use `logger.error()` for operational errors
- Use `logger.warning()` for recoverable issues
- Return appropriate HTTP status codes in API routes

```python
# Good - API error handling
try:
    results = search_engine.search(q, limit=limit)
    return jsonify(results), 200
except Exception as e:
    logger.exception("Search error")
    return jsonify({"status": "error", "message": str(e)}), 500

# Good - Expected error cases
if not q:
    return jsonify({"status": "error", "message": "Query required"}), 400
```

### Logging

- Use module-level logger: `logger = logging.getLogger(__name__)`
- Use appropriate log levels:
  - `logger.debug()`: Detailed diagnostic info (production: off)
  - `logger.info()`: Confirmation things work as expected
  - `logger.warning()`: Something unexpected happened but recoverable
  - `logger.error()`: Serious problem, functionality affected
  - `logger.exception()`: Error with stack trace

```python
import logging

logger = logging.getLogger(__name__)

def process_task(task_id: str) -> bool:
    """Process a task."""
    logger.info(f"Processing task {task_id}")
    try:
        # ... processing
        return True
    except Exception as e:
        logger.exception(f"Failed to process task {task_id}")
        return False
```

### Configuration

- Use `pydantic_settings.BaseSettings` for configuration
- Use environment variables with `Field(alias="...")`
- Validate configuration at startup

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    debug: bool = Field(default=True, alias="OPENRECALL_DEBUG")
    port: int = Field(default=8083, alias="OPENRECALL_PORT")
    
    model_config = {
        "env_prefix": "",
        "populate_by_name": True,
    }

settings = Settings()
```

### Database Operations

- Use SQLite with connection pooling patterns
- Always close connections or use context managers
- Log database errors with specific context

### Thread Safety

- Use threading locks for shared mutable state
- Use `@property` with care in multithreaded contexts

```python
from threading import Lock

class RuntimeSettings:
    _lock = Lock()
    
    @property
    def config(self) -> dict:
        with self._lock:
            return self._config.copy()
```

## Project Structure

```
openrecall/
├── __init__.py
├── main.py              # Combined server+client entry point
├── client/              # Screenshot capture client
│   ├── recorder.py      # Screenshot capture (Producer)
│   ├── buffer.py        # Local disk queue
│   ├── uploader.py      # Background upload (Consumer)
│   └── consumer.py      # Upload coordination
├── server/              # Flask API server
│   ├── api.py           # REST API endpoints
│   ├── app.py           # Flask application setup
│   ├── worker.py        # Background AI processing worker
│   ├── nlp.py           # Embedding generation
│   ├── ai_engine.py     # Vision language model
│   ├── database/        # SQLite & LanceDB integration
│   │   ├── sql.py       # SQLite operations
│   │   └── vector_store.py  # Vector database
│   ├── search/          # Search pipeline
│   │   └── engine.py    # Hybrid search (vector + FTS + rerank)
│   ├── services/        # Business logic services
│   │   └── reranker.py # Cross-encoder reranking
│   └── utils/           # Utilities
│       ├── query_parser.py
│       ├── fusion.py
│       └── keywords.py
└── shared/              # Shared code
    ├── config.py        # Pydantic settings
    ├── models.py        # Pydantic models
    └── utils.py        # Common utilities

tests/
├── conftest.py         # Pytest fixtures
├── test_phase*.py      # Integration tests
├── test_*.py           # Unit tests
└── test_*_integration.py
```

## Test Markers

Defined in `pytest.ini`:

- `unit`: Unit tests
- `integration`: Module/integration tests
- `e2e`: End-to-end system tests
- `perf`: Performance benchmarks
- `security`: Security tests
- `model`: Tests requiring ML models (may download)
- `manual`: Manual test scripts (not automated)

Default test run excludes: `e2e`, `perf`, `security`, `model`, `manual`

## Common Development Patterns

### Adding a New API Endpoint

```python
from flask import Blueprint, jsonify, request

api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.route("/new_endpoint", methods=["GET"])
def new_endpoint():
    """Endpoint description."""
    # Input validation
    param = request.args.get("param")
    if not param:
        return jsonify({"error": "param required"}), 400
    
    # Business logic
    result = do_something(param)
    
    # Return JSON response
    return jsonify(result), 200
```

### Adding a New Test

```python
import pytest

class TestFeatureName:
    """Tests for feature_name."""
    
    @pytest.fixture
    def setup_fixture(self, tmp_path):
        """Create test fixtures."""
        return tmp_path / "test_data"
    
    def test_something(self, setup_fixture):
        """Test description."""
        # Arrange
        obj = MyClass()
        
        # Act
        result = obj.do_something()
        
        # Assert
        assert result == expected
```

## Environment Variables

Key configuration options (see `openrecall/shared/config.py` for full list):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENRECALL_DEBUG` | true | Enable debug logging |
| `OPENRECALL_PORT` | 8083 | Server port |
| `OPENRECALL_DATA_DIR` | ~/MRS | Server data directory |
| `OPENRECALL_CLIENT_DATA_DIR` | ~/MRC | Client buffer directory |
| `OPENRECALL_DEVICE` | cpu | AI inference device (cpu, cuda, mps) |
| `OPENRECALL_AI_PROVIDER` | local | AI provider (local, dashscope, openai) |
| `OPENRECALL_CAPTURE_INTERVAL` | 10 | Screenshot interval (seconds) |

## Running Tests with Different Configurations

```bash
# Activate conda environment
conda activate old

# Use custom data directory for tests
OPENRECALL_DATA_DIR=/tmp/test_data pytest

# Run with debug logging
OPENRECALL_DEBUG=true pytest -v

# Test with specific AI provider
OPENRECALL_AI_PROVIDER=openai OPENRECALL_AI_API_KEY=sk-... pytest
```
