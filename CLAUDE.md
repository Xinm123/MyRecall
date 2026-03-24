# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MyRecall v3 is a privacy-first alternative to proprietary digital memory solutions (Windows Recall, Rewind.ai). It captures digital history through automatic screenshots and makes them searchable via natural language queries.

**Core Principles:**
- **Edge-Centric Architecture**: Host (capture) and Edge (processing) are separate processes
- **Vision + OCR + Accessibility**: Uses macOS AX (accessibility) for text extraction with OCR as fallback
- **AX-first**: Client collects accessibility data first; if AX succeeds → `text_source='accessibility'`, else OCR fallback → `text_source='ocr'`
- **Privacy-First**: All data stays local, no cloud required
- **FTS5 Search**: Full-text search with metadata filtering

**Reference Implementation:**
- `_ref/screenpipe/` contains the screenpipe Rust implementation (reference for architectural decisions)

## Commands

### Running the Application

**Two separate processes:**

```bash
# Server (Edge) - Terminal 1
./run_server.sh --debug

# Client (Host) - Terminal 2
./run_client.sh --debug
```

Open browser: http://localhost:8883

**Configuration:**
- Server: `myrecall_server.env` or environment variables
- Client: `myrecall_client.env` or environment variables
- Key settings: `OPENRECALL_SERVER_DATA_DIR` (~/MRS), `OPENRECALL_CLIENT_DATA_DIR` (~/MRC)

### Testing

```bash
# Run all default tests (unit + integration, excludes e2e/perf/security/model/manual)
pytest

# Run specific test categories
pytest -m unit           # Unit tests (no external dependencies)
pytest -m integration    # Integration tests (requires running Edge server)
pytest -m e2e           # End-to-end tests
pytest -m perf          # Performance benchmarks
pytest -m security      # Security tests
pytest -m model         # Tests requiring AI models

# Run specific test file
pytest tests/test_p1_s1_ingest.py -v

# Run with coverage
pytest --cov=openrecall --cov-report=term-missing
```

**Note:** Integration tests require a running Edge server: `./run_server.sh --debug`

### Installation

```bash
pip install -e .
pip install -e ".[test]"    # Include test dependencies
```

## Architecture

### Host (Client) - `openrecall.client`

**Responsibility:** Capture + Spool + Upload + Web UI Server (port 8883)

**Components:**
- **Recorder**: Event-driven screenshot capture
  - Triggers: `idle`, `app_switch`, `manual`, `click`
  - Debounce: Three-layer debouncing (click: 3000ms, trigger: 3000ms, capture: 3000ms)
  - Idle fallback: `idle_capture_interval_ms=60000ms`
- **Spool**: Disk queue for reliability (`~/MRC/spool/`)
  - Format: JPEG (`.jpg`/`.jpeg`) + JSON metadata
  - Atomic writes, idempotent retry
- **Uploader**: Background consumer, posts to Edge `/v1/ingest`
- **Web Server**: Flask app on port 8883 serving Jinja2 templates; browser JS fetches API from Edge (port 8083) via CORS

**Web Routes (served by Client):**
- `/` (Grid), `/search`, `/timeline` — Jinja2 templates
- `/vendor/*` — Alpine.js static assets
- `/screenshots/*` — Proxy to Edge `/v1/frames/` (for legacy fallback)

**Web Server:** Flask app in `openrecall/client/web/app.py` serving templates from `openrecall/client/web/templates/`

**Entry Point:** `python -m openrecall.client`

### Edge (Server) - `openrecall.server`

**Responsibility:** Processing + API + Search (pure API, no Web UI)

**Components:**
- **Ingest API**: `POST /v1/ingest` (idempotent)
- **Worker**: Processing worker (`V3ProcessingWorker` for OCR mode, `DescriptionWorker` for frame descriptions)
- **Database**:
  - `~/MRS/db/edge.db`: Frames metadata + FTS5 tables (frames_fts, ocr_text_fts, accessibility_fts)
  - `~/MRS/fts.db`: Legacy schema (used by old API layer)
  - `~/MRS/frames/`: JPEG snapshots
- **Search Engine**: FTS5 + metadata filtering (P1)
  - Filters: time range, app_name, window_name, browser_url, focused
  - `content_type` parameter: `ocr`, `accessibility`, or `all` (default)
  - No vector embeddings in production P1 (reserved for P2+ experimental)
- **CORS Middleware**: Echo-back `Origin` header for cross-origin browser requests from Client web UI

**API Routes:** `/v1/*`, `/api/*` — all responses include `Access-Control-Allow-Origin: <browser-origin>`

**Entry Point:** `python -m openrecall.server`

### Key Data Structures

**Frames Table** (`edge.db`):
```sql
- frame_id (TEXT PRIMARY KEY)
- capture_id (TEXT UNIQUE, idempotency key)
- timestamp (TEXT ISO8601 UTC)
- app_name, window_name, browser_url
- monitor_index, device_id
- capture_trigger (idle/app_switch/manual/click)
- accessibility_text (text from AX, if AX-first succeeded)
- ocr_text (text from OCR fallback)
- text_source ('accessibility'|'ocr')
- accessibility_tree_json (full AX tree as JSON)
- processing_status (pending/processing/completed/failed)
- event_ts (capture event timestamp, separate from frame timestamp)
```

**FTS5 Tables**:
- `ocr_text_fts`: Full-text index on OCR text
- `accessibility_fts`: Full-text index on accessibility text (includes browser_url)
- `frames_fts`: Full-text index on metadata only (app_name, window_name, browser_url, focused)

## Key Architecture Decisions

Key decisions embedded in this document:
- **Edge-Centric**: Host captures/uploads, Edge processes/indexes/searches
- **Vision + AX + OCR**: AX-first text extraction with OCR fallback; both indexed separately
- **FTS5 Search**: Full-text search on both OCR and accessibility text via `content_type` filter

Architecture baselines: `docs/baselines/` (chat, search)

## Database Migrations

Migrations are in `openrecall/server/database/migrations/`:
- Run automatically on server startup
- Use SQLite with FTS5 extensions
- Timestamped migration files: `YYYYMMDDHHMMSS_description.sql`

**To add a migration:**
1. Create file: `20260316120000_description.sql`
2. Write SQL (forward migration only)
3. Test with: `pytest tests/test_v3_migrations_bootstrap.py`

## Development Workflow

### Adding New Features

1. **Check current plans**: `docs/superpowers/plans/` for active implementation plans
2. **Read specs**: `docs/superpowers/specs/` for design specifications
3. **Write tests first**: Follow TDD (minimum 80% coverage)
4. **Update docs**: If changing API contracts or architecture

### Code Structure

```
openrecall/
├── client/           # Host process
│   ├── __main__.py  # Entry point
│   ├── events/      # Event capture (macOS CGEventTap)
│   ├── recorder.py  # Screenshot capture + AX collection
│   ├── spool.py     # Disk queue
│   ├── uploader.py  # Edge upload consumer
│   ├── hash_utils.py  # Frame deduplication (hash)
│   ├── accessibility/  # macOS AX (accessibility) text extraction
│   │   ├── service.py  # AX collection entrypoint
│   │   ├── macos.py    # macOS AX API bindings
│   │   ├── policy.py   # AX vs OCR decision logic
│   │   └── types.py    # AccessibilityDecision types
│   └── web/         # Flask web UI (port 8883)
│       ├── app.py
│       └── templates/
├── server/          # Edge process
│   ├── __main__.py  # Entry point
│   ├── app.py       # Flask app
│   ├── api.py       # Legacy API (410 Gone)
│   ├── api_v1.py    # v1 API endpoints (/v1/*)
│   ├── worker.py    # Legacy ProcessingWorker
│   ├── database/    # SQLite + migrations
│   │   ├── frames_store.py  # v3 FramesStore (edge.db)
│   │   └── sql.py          # Legacy SQLStore (fts.db)
│   ├── search/      # FTS5 search engine
│   ├── processing/  # V3ProcessingWorker, OCR processor
│   └── description/ # DescriptionWorker (frame descriptions)
└── shared/          # Common utilities
    ├── config.py    # Settings management
    └── models.py    # Data models
```

### Environment Variables

Key settings (see `openrecall/shared/config.py`):
- `OPENRECALL_SERVER_DATA_DIR`: Edge data directory (default: ~/MRS)
- `OPENRECALL_CLIENT_DATA_DIR`: Host spool directory (default: ~/MRC)
- `OPENRECALL_PORT`: Edge API server port (default: 8083, API only — web UI disabled)
- `OPENRECALL_CLIENT_WEB_PORT`: Client web UI port (default: 8883)
- `OPENRECALL_DEBUG`: Enable debug logging
- `OPENRECALL_AI_PROVIDER`: AI provider (local/dashscope/openai)
- `OPENRECALL_DEVICE`: Inference device (cpu/cuda/mps)
- `OPENRECALL_TRIGGER_DEBOUNCE_MS`: Debounce for APP_SWITCH/IDLE/MANUAL events (default: 3000)
- `OPENRECALL_CLICK_DEBOUNCE_MS`: Debounce for CLICK events (default: 3000)
- `OPENRECALL_CAPTURE_DEBOUNCE_MS`: Global capture debounce (default: 3000)
- `OPENRECALL_IDLE_CAPTURE_INTERVAL_MS`: Idle fallback interval (default: 60000)

## Testing Strategy

**Test Markers** (see `pytest.ini`):
- `unit`: Unit tests, no external dependencies
- `integration`: Requires running Edge server
- `e2e`: End-to-end system tests
- `perf`: Performance benchmarks
- `security`: Security tests
- `model`: Tests requiring AI models/large downloads
- `manual`: Manual test scripts
- `search`: Search engine tests

**Test Organization:**
- `tests/` - Active tests
- `tests/archive/` - Deprecated/archived tests
- `scripts/acceptance/` - Acceptance test scripts

**Running Tests:**
- Default: `pytest` runs unit + integration, excludes heavy tests
- Integration tests need: `./run_server.sh --debug` in separate terminal
- See `tests/README.md` for detailed guide

## Image Format Contract

**P1 Contract (v3):**
- **Capture**: JPEG format (`.jpg`/`.jpeg`)
- **Ingest API**: Accepts `image/jpeg`
- **Frame Storage**: JPEG in `~/MRS/frames/`
- **Frame API**: Returns `image/jpeg`
- **Legacy Support**: Reads `.webp` only for draining old spool

## API Contracts

**v1 API Endpoints** (`/v1/*`):
- `POST /v1/ingest`: Upload frame (idempotent, supports AX-canonical payload)
- `GET /v1/frames/<frame_id>`: Retrieve frame JPEG
- `GET /v1/health`: Health check
- `GET /v1/ingest/queue/status`: Queue status
- `GET /v1/search`: Search with `content_type` filter (`ocr`/`accessibility`/`all`)
- `GET /v1/search/counts`: Get result counts by content type

**Legacy API** (`/api/*`):
- Deprecated, returns 410 Gone for all endpoints
- All functionality migrated to `/v1/*`

See `docs/archive/v3/http_contract_ledger.md` for complete API documentation (archived).

## Performance Characteristics

**Capture Frequency:**
- P1/P2: 1Hz maximum (intentional deviation from screenpipe's 5Hz)
- Debounce: Three-layer (click 3000ms, trigger 3000ms, capture 3000ms)
- Idle fallback: 60000ms timeout

**Search:**
- FTS5-based full-text search
- B-tree indexes on metadata (app, window, timestamp)
- P95 latency target: < 200ms for typical queries

**Queue Processing:**
- LIFO mode when queue >= threshold (newest first)
- FIFO mode otherwise (oldest first)
- Backpressure protection via bounded channels

## Common Patterns

### Adding a New Database Field

1. Create migration: `openrecall/server/database/migrations/YYYYMMDDHHMMSS_add_field.sql`
2. Update `FramesStore` class in `openrecall/server/database/frames_store.py`
3. Update API contracts in `openrecall/server/api_v1.py`
4. Update tests in `tests/test_p1_s1_frames.py`
5. Run migrations test: `pytest tests/test_v3_migrations_bootstrap.py`

### Adding a New Capture Trigger

1. Update `CaptureTrigger` enum in `openrecall/client/events/base.py`
2. Add event detection in `openrecall/client/events/`
3. Update recorder logic in `openrecall/client/recorder.py`
4. Add tests in `tests/test_p1_s2a_trigger_coverage.py`
5. Update acceptance script: `scripts/acceptance/p1_s2a_local.sh`

### Debugging Upload Issues

1. Check spool directory: `ls ~/MRC/spool/`
2. Check uploader logs: Look for `[Uploader]` entries
3. Verify Edge server running: `curl http://localhost:8083/v1/health`
4. Check queue status: `curl http://localhost:8083/v1/ingest/queue/status`

## Reference: screenpipe

The `_ref/screenpipe/` directory contains the screenpipe Rust implementation for reference:

**Key Differences:**
- MyRecall: Python, split into Host/Edge processes
- screenpipe: Rust, single-process local
- Both: Vision-only, FTS-based search

**When Consulting screenpipe:**
- Check architecture patterns (e.g., event-driven capture)
- Validate design decisions (e.g., FTS-first search)
- Compare performance characteristics
- Look for edge cases in cross-platform support

## Current Development Phase

Active implementation plans: `docs/superpowers/plans/`
Design specifications: `docs/superpowers/specs/`
Architecture baselines: `docs/baselines/`
