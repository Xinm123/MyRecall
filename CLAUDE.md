# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MyRecall v3 is a privacy-first alternative to proprietary digital memory solutions (Windows Recall, Rewind.ai). It captures digital history through automatic screenshots and makes them searchable via natural language queries.

**Core Principles:**
- **Edge-Centric Architecture**: Host (capture) and Edge (processing) are separate processes
- **Vision-Only, OCR-Only**: Uses OCR for text extraction
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

**Responsibility:** Capture + Spool + Upload

**Components:**
- **Recorder**: Event-driven screenshot capture
  - Triggers: `idle`, `app_switch`, `manual`, `click`
  - Debounce: `min_capture_interval_ms=1000ms`
  - Idle fallback: `idle_capture_interval_ms=30000ms`
- **Spool**: Disk queue for reliability (`~/MRC/spool/`)
  - Format: JPEG (`.jpg`/`.jpeg`) + JSON metadata
  - Atomic writes, idempotent retry
- **Uploader**: Background consumer, posts to Edge `/v1/ingest`

**Entry Point:** `python -m openrecall.client`

### Edge (Server) - `openrecall.server`

**Responsibility:** Processing + API + Search

**Components:**
- **Ingest API**: `POST /v1/ingest` (idempotent)
- **Worker**: Async OCR processing with task queue
- **Database**:
  - `~/MRS/db/edge.db`: Frames metadata, task queue
  - `~/MRS/fts.db`: FTS5 full-text index
  - `~/MRS/frames/`: JPEG snapshots
- **Search Engine**: FTS5 + metadata filtering (P1)
  - Filters: time range, app_name, window_name, browser_url, focused
  - No vector embeddings in production P1 (reserved for P2+ experimental)

**Entry Point:** `python -m openrecall.server`

**Web Routes:**
- Web UI (served by Client on port 8883): `/` (Grid), `/search`, `/timeline` — browser fetches API from Edge directly
- Server (port 8083) serves API only: `/v1/*`, `/api/*` — web UI routes are disabled (`DISABLE_SERVER_WEB=True`)

### Key Data Structures

**Frames Table** (`edge.db`):
```sql
- frame_id (TEXT PRIMARY KEY)
- capture_id (TEXT UNIQUE, idempotency key)
- timestamp (TEXT ISO8601 UTC)
- app_name, window_title, browser_url
- monitor_index, device_id
- capture_trigger (idle/app_switch/manual/click)
- ocr_text
- processing_status (pending/processing/completed/failed)
- event_ts (capture event timestamp, separate from frame timestamp)
```

**FTS5 Tables**:
- `ocr_text_fts`: Full-text index on OCR text
- `frames_fts`: Full-text index on metadata + OCR

## Key Architecture Decisions (ADRs)

Located in `docs/v3/adr/`:

1. **ADR-0001**: Edge-Centric Responsibility Split
   - Host: capture + spool + upload only
   - Edge: processing + index + search + chat

2. **ADR-0005**: Vision-Only Search (aligns with screenpipe)
   - FTS + metadata filtering
   - No vector search in production
   - Embeddings reserved for P2+ experimental use

3. **OCR-Only (OQ-043)**: Accessibility schema reserved for v4, not in v3 data flow

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

1. **Check roadmap**: `docs/v3/roadmap.md` for current phase
2. **Read ADRs**: `docs/v3/adr/` for architectural constraints
3. **Write tests first**: Follow TDD (minimum 80% coverage)
4. **Update docs**: If changing API contracts or architecture

### Code Structure

```
openrecall/
├── client/           # Host process
│   ├── events/      # Event capture (macOS CGEventTap)
│   ├── recorder.py  # Screenshot capture
│   ├── spool.py     # Disk queue
│   └── uploader.py  # Edge upload consumer
├── server/          # Edge process
│   ├── api.py       # Legacy API routes
│   ├── api_v1.py    # v1 API endpoints (/v1/*)
│   ├── worker.py    # Async OCR processing
│   ├── database/    # SQLite + migrations
│   ├── search/      # FTS5 search engine
│   └── ocr/         # OCR providers
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
- `OPENRECALL_MIN_CAPTURE_INTERVAL_MS`: Debounce interval (default: 2000)
- `OPENRECALL_IDLE_CAPTURE_INTERVAL_MS`: Idle fallback (default: 30000)

## Testing Strategy

**Test Markers** (see `pytest.ini`):
- `unit`: Unit tests, no external dependencies
- `integration`: Requires running Edge server
- `e2e`: End-to-end system tests
- `perf`: Performance benchmarks
- `security`: Security tests
- `model`: Tests requiring AI models/large downloads
- `manual`: Manual test scripts

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
- `POST /v1/ingest`: Upload frame (idempotent)
- `GET /v1/frames/<frame_id>`: Retrieve frame JPEG
- `GET /v1/health`: Health check
- `GET /v1/ingest/queue/status`: Queue status

**Legacy API** (`/api/*`):
- Deprecated, redirects to `/v1/*` with 301/308
- Logs `[DEPRECATED]` warning

See `docs/v3/http_contract_ledger.md` for complete API documentation.

## Performance Characteristics

**Capture Frequency:**
- P1/P2: 1Hz maximum (intentional deviation from screenpipe's 5Hz)
- Debounce: 1000ms minimum between captures
- Idle fallback: 30000ms timeout

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

1. Update `CaptureTrigger` enum in `openrecall/shared/models.py`
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

See `docs/v3/roadmap.md` for current phase:

**Phase 1**: Local simulated Edge (process isolation)
- P1-S1: Basic ingest pipeline ✓
- P1-S2a: Event-driven capture
- P1-S2a+: Permission stability closure
- P1-S2b: Capture completion
- P1-S3+: OCR processing and beyond

Each stage has explicit gates in `docs/v3/gate_baseline.md`.
