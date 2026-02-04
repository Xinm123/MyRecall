# Repository Guidelines

## Project Structure & Module Organization

- `openrecall/`: Python package.
  - `openrecall/server/`: Flask server (REST API + Web UI templates).
  - `openrecall/client/`: screenshot capture + upload.
  - `openrecall/shared/`: shared config/logging/models.
- `tests/`: pytest suite. `tests/manual/` contains opt-in scripts; `tests/v2/` holds legacy/regression coverage.
- `docs/` and `images/`: documentation and static assets.
- Root helper scripts: `run_server.sh`, `run_client.sh`, `run_phase8_*_tests.sh`.

## Build, Test, and Development Commands

- Python: 3.11+ (see `.python-version`; CI uses 3.12)
- Create a venv: `python -m venv .venv && source .venv/bin/activate`
- Install (editable): `python -m pip install -e ".[test]"`
- Run (combined mode): `python -m openrecall.main`
- Run (split processes): `python -m openrecall.server` and `python -m openrecall.client`
  - With env files: `./run_server.sh --env=myrecall_server.env` and `./run_client.sh --env=myrecall_client.env`
- Unit+integration tests: `pytest` (default selection excludes `e2e`, `perf`, `security`, `model`, `manual`)
- Coverage gate: `pytest --cov=openrecall --cov-fail-under=80`
- Security checks: `python -m pip install -e ".[security]" && bandit -q -r openrecall && pip-audit`
- E2E (Playwright): `python -m pip install -e ".[test,e2e]" && python -m playwright install chromium && pytest -m e2e`

## Coding Style & Naming Conventions

- Python: 4-space indentation, PEP 8, and type hints for new/changed public functions.
- Naming: modules/functions `snake_case`, classes `CamelCase`, constants `UPPER_SNAKE_CASE`.
- Configuration: add settings in `openrecall/shared/config.py` and expose via `OPENRECALL_*` environment variables.

## Testing Guidelines

- Place new tests under `tests/` (pytest is configured with `testpaths = tests`).
- Use pytest markers consistently (`unit`, `integration`, `e2e`, `perf`, `security`, `model`, `manual`) and keep default tests offline/deterministic.

## Commit & Pull Request Guidelines

- Commit subjects in this repo are short and often phase/version tagged (examples: `phase9-api`, `v3-0`). Keep the first line imperative and scoped.
- PRs should include: what changed, how to run it locally, and test output. Add screenshots/GIFs for Web UI changes.
- Never commit secrets: keep API keys out of git (use placeholders in `*.env` and set real values locally via environment variables).

## Agent-Specific Notes (Optional)

- Prefer `rg` for search and keep changes focused; update/extend tests when touching server APIs or config.
- Avoid introducing downloads or heavyweight model use into the default pytest run; gate those behind the existing markers.
