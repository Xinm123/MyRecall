# AGENTS.md - MyRecall Codebase Guide for AI Agents

## Project Overview

MyRecall is a local-first digital memory system for continuous screen capture, OCR indexing, and timeline/search retrieval. Python + Flask, client-server architecture.

## Build/Test Commands

```bash
conda activate v3                        # Activate conda environment (recommended)
```

### Startup (Two Terminals)

**Terminal A (Server):**
```bash
conda activate v3
cd /Users/pyw/new/MyRecall
./run_server.sh --debug
```

**Terminal B (Client):**
```bash
conda activate v3
cd /Users/pyw/new/MyRecall
./run_client.sh --debug
```

### Testing
```bash
python3 -m pytest                        # Run all (excludes e2e/perf/security/model/manual)
python3 -m pytest tests/test_phase0_gates.py -v                              # Single file
python3 -m pytest tests/test_phase0_gates.py::TestGateF01SchemaМigrationSuccess -v  # Single test
python3 -m pytest -k "upload" -v         # Pattern match
python3 -m pytest --cov=openrecall --cov-report=html                         # With coverage
```

**Test markers** (pytest.ini): `unit`, `integration`, `e2e`, `perf`, `security`, `model`, `manual`

## Project Structure

```
openrecall/
  client/         # Recording, buffering, upload
  server/         # Flask app, API, workers, database
  shared/         # Config, utils, logging
tests/            # All test files
v3/               # Planning docs, ADRs, milestones
```

## Code Style

### Imports (order: stdlib → third-party → local)
```python
import os
from pathlib import Path
from typing import Optional

from flask import Flask
from pydantic import Field

from openrecall.shared.config import settings
from openrecall.server.database import SQLStore
```

### Formatting
- Python 3.9-3.12, 4 spaces indent, ~100 char lines
- Double quotes, trailing commas in multi-line structures

### Naming
- Files: `snake_case.py` | Classes: `PascalCase` | Functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE` | Private: `_prefix`

### Type Hints & Docstrings
```python
def process_frame(frame_data: bytes, timestamp: float) -> Optional[dict]:
    """Process a video frame.
    
    Args:
        frame_data: Raw frame bytes
        timestamp: Unix timestamp
    Returns:
        Processed result dict or None
    """
```

### Error Handling
```python
try:
    result = do_something()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    # Handle gracefully
```
- Use `logging` module, avoid bare `except:`

### Configuration
- All settings via pydantic-settings in `openrecall/shared/config.py`
- Env vars prefixed `OPENRECALL_*`
- Access: `from openrecall.shared.config import settings`

### Database
- SQLite via `SQLStore` in `openrecall/server/database/`
- Always use parameterized queries (never f-strings for SQL)

### Testing Patterns
```python
@pytest.fixture
def flask_client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
```
- Use `tmp_path` for filesystem, `monkeypatch` for env vars
- Reload modules after env changes (see `conftest.py`)

## Key Files

| Purpose | Path |
|---------|------|
| Flask app | `openrecall/server/app.py` |
| Config | `openrecall/shared/config.py` |
| Video recorder | `openrecall/client/video_recorder.py` |
| Database | `openrecall/server/database/sql.py` |
| API routes | `openrecall/server/api.py`, `openrecall/server/api_v1.py` |
| Test fixtures | `tests/conftest.py` |

## Environment Variables

Key vars (full list in `openrecall/shared/config.py`):
- `OPENRECALL_DEBUG`, `OPENRECALL_PORT` (default: 8083)
- `OPENRECALL_SERVER_DATA_DIR`, `OPENRECALL_CLIENT_DATA_DIR`
- `OPENRECALL_API_URL`, `OPENRECALL_RECORDING_MODE` (`auto|video|screenshot`)

## Common Gotchas

1. **Config reload in tests**: `importlib.reload(openrecall.shared.config)` after env changes
2. **FFmpeg required**: Video pipeline needs `ffmpeg` in PATH
3. **macOS permissions**: Screen Recording permission required for capture
4. **Port conflicts**: 8083 default, 18083 with env files

## Reference Dependency Policy

`screenpipe` is reference-only - do NOT add runtime/build/test dependency. Manual comparison allowed.
