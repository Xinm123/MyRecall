# AGENTS Guide: OpenRecall

This file is for coding agents working in `/Users/pyw/old/MyRecall`.
Use it as the operational source of truth for commands and coding conventions.

## Project Snapshot

- OpenRecall is a privacy-first local memory system (screenshot capture + AI + search).
- Architecture is split into `openrecall/client` and `openrecall/server`.
- Main entry points are module runs (`python -m openrecall.*`) and wrapper scripts.

## Build / Run Commands

Use the active Python environment first (commonly `conda activate old`).

```bash
# Separate mode (wrapper scripts with env loading)

# Run server (Terminal 1)
./run_server.sh --debug

# Run client (Terminal 2)
./run_client.sh --debug
```

Notes:
- `run_server.sh` executes `-m openrecall.server` and loads `myrecall_server.env` by default.
- `run_client.sh` executes `-m openrecall.client` and loads `myrecall_client.env` by default.
- Both scripts support `--env=/abs/path/to/file.env`.

## Test Commands (Pytest)

Default `pytest` excludes markers: `e2e`, `perf`, `security`, `model`, `manual`.
(`pytest.ini` uses `--strict-markers` and marker filtering in `addopts`.)

```bash
# Run default suite
pytest

# Run one test file
pytest tests/test_phase5_buffer.py

# Run one class or one test function
pytest tests/test_phase5_buffer.py::TestLocalBuffer
pytest tests/test_phase5_buffer.py::TestLocalBuffer::test_enqueue_creates_files

# Run tests by substring
pytest -k "test_enqueue_creates_files"

# Marker-based runs
pytest -m unit
pytest -m integration
pytest -m "not e2e"

# Verbose
pytest -v

# Coverage
pytest --cov=openrecall --cov-report=term-missing
pytest --cov=openrecall --cov-fail-under=80
```

## Lint / Type Check Reality

- No root `pyproject.toml`, `setup.cfg`, `tox.ini`, or `Makefile` defines lint/type commands.
- No canonical repo command for `ruff`, `flake8`, `mypy`, or `pyright` was found.
- Treat `pytest --strict-markers` + passing tests as the enforced quality baseline.

## Python Style Guide (Repository-Observed)

### Imports

Use three import blocks with blank lines:
1) standard library
2) third-party libraries
3) `openrecall.*` local imports

This pattern is used in `openrecall/server/api.py` and `openrecall/client/buffer.py`.

### Formatting

- Use 4-space indentation.
- Keep lines readable and split long literals/calls across lines with trailing commas.
- Match surrounding style; this repository has no enforced formatter config file at root.

### Type Hints

- Add type hints to function signatures and significant locals.
- The codebase contains both `Optional[T]` and `T | None`; prefer consistency with touched file.
- Use concrete collection typing where useful (e.g., `list[str]`, `dict[str, int]`).

### Naming

- Classes: PascalCase (`SQLStore`, `ProcessingWorker`).
- Functions/variables: snake_case (`get_pending_count`, `image_path`).
- Constants: UPPER_SNAKE_CASE.
- Internal helpers/private state: leading underscore (`_serialize_metadata`, `_lock`).

### Docstrings

- Use triple-quoted docstrings on modules/classes/public functions.
- Google-style sections (`Args`, `Returns`, `Raises`) are common and preferred.
- Keep docstrings practical; describe behavior and important constraints.

### Logging

- Define module logger: `logger = logging.getLogger(__name__)`.
- Use levels consistently:
  - `debug`: noisy diagnostics
  - `info`: lifecycle and normal state transitions
  - `warning`: recoverable problems
  - `error`: failures with degraded behavior
  - `exception`: caught exceptions requiring traceback

### Error Handling

- Validate API input early and return explicit 4xx errors.
- In Flask routes, use `logger.exception(...)` in broad exception handlers and return JSON errors.
- Prefer specific exceptions where practical (`sqlite3.Error` in DB code).
- Preserve graceful fallbacks where existing modules already use them (NLP/worker paths).

### Database and Concurrency

- Use context-managed SQLite connections (`with sqlite3.connect(...) as conn:`).
- Commit after write operations explicitly.
- Protect shared runtime mutable state with locks (`runtime_settings._lock`).

## Testing Conventions

- Test files use `test_*.py` naming.
- Test classes often use `Test*`; test functions use `test_*`.
- Prefer pytest fixtures (`conftest.py` + local fixtures).
- Marker usage is active and strict:
  - `unit`, `integration`, `e2e`, `perf`, `security`, `model`, `manual`
- Some modules apply markers via module-level `pytestmark`.

## Configuration Conventions

- Runtime config is centralized in `openrecall/shared/config.py` (`pydantic-settings`).
- Environment variables use `OPENRECALL_*` aliases via `Field(alias=...)`.
- Paths are `Path`-based and expanded/resolved during settings validation.

Common vars:
- `OPENRECALL_DEBUG`
- `OPENRECALL_PORT`
- `OPENRECALL_SERVER_DATA_DIR`
- `OPENRECALL_CLIENT_DATA_DIR`
- `OPENRECALL_AI_PROVIDER`
- `OPENRECALL_DEVICE`

## Agent Rules from Cursor / Copilot

- No `.cursorrules` file found.
- No `.cursor/rules/` directory found.
- No `.github/copilot-instructions.md` found.

If these files are added later, update this guide and treat them as higher-priority agent policy.

## Practical Guardrails for Agents

- Make focused, minimal edits; avoid broad refactors during bug fixes.
- Do not invent commands absent from repo docs/config.
- Prefer existing patterns in touched modules over introducing new styles.
- Run targeted tests first (single file/test), then broader suite if needed.
- Never commit unless explicitly requested by the user.
