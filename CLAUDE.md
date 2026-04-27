# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

MyRecall v3 is a privacy-first digital memory alternative to Windows Recall / Rewind.ai. It captures screenshots automatically and makes them searchable via natural language.

**Core Principles:**
- **Edge-Centric**: Host (capture) and Edge (processing/search) are separate processes
- **AX-first**: Client collects macOS accessibility text first; if AX succeeds → `text_source='accessibility'`, else OCR fallback → `text_source='ocr'`
- **Hybrid Search**: FTS5 full-text + LanceDB vector search with RRF fusion
- **Privacy-First**: All data stays local by default
- **UTC+8**: `local_timestamp` is the primary query/display dimension (ISO8601 without offset)

**Reference:** `_ref/screenpipe/` contains the upstream Rust implementation for architectural comparison.

## Quick Start

```bash
# Terminal 1 — Edge (processing + API)
./run_server.sh --mode local --debug

# Terminal 2 — Host (capture + web UI)
./run_client.sh --mode local --debug

# Open http://localhost:8889
```

**Configuration:** TOML files (`server-local.toml`, `client-local.toml`, `client-remote.toml`). `--config=/path` takes precedence over `--mode`. All settings are in `openrecall/shared/config.py`.

```bash
pip install -e .
pip install -e ".[test]"
```

## Architecture

### Host (Client) — `openrecall.client`

Responsibility: Capture + Spool + Upload + Web UI (port 8889)

| Component | File | Key Detail |
|-----------|------|------------|
| Recorder | `recorder.py` | Event-driven capture (idle/app_switch/manual/click); three-layer debounce (click/trigger/capture) via `AtomicInt` ctypes; idle fallback 60s |
| runtime_config | `runtime_config.py` | Hot-reload SQLite-backed config; SQLite > TOML priority; `threading.Event` wait/notify |
| Spool | `spool.py` | Disk queue `~/.myrecall/client/spool/`; JPEG + JSON; atomic writes |
| Uploader | `uploader.py` | Background consumer → Edge `POST /v1/ingest` |
| Web Server | `web/app.py` | Flask on 8889; Jinja2 templates; JS calls Edge API (port 8083) via CORS |
| Chat | `chat/` | Pi agent process; SSE streaming; grounded in visual history |

Web routes: `/` (Grid), `/search`, `/timeline`, `/chat`, `/settings`.
Chat API routes: `/chat/api/*` — see `openrecall/client/chat/routes.py` for all endpoints.

**Entry:** `python -m openrecall.client`

### Edge (Server) — `openrecall.server`

Responsibility: Processing + API + Search (pure API, no Web UI)

| Component | File | Key Detail |
|-----------|------|------------|
| Ingest API | `api_v1.py` | `POST /v1/ingest`; idempotent via `capture_id` |
| OCR Worker | `processing/v3_worker.py` | `V3ProcessingWorker`; AX-first, OCR fallback |
| Description Worker | `description/worker.py` | `DescriptionWorker`; AI-generated frame descriptions |
| Embedding Worker | `embedding/worker.py` | `EmbeddingWorker`; LanceDB + qwen3-vl-embedding |
| Search | `search/engine.py` + `search/hybrid_engine.py` | FTS5 (`frames_fts`) + vector (LanceDB) with RRF fusion |
| Frames Store | `database/frames_store.py` | Primary SQLite interface for `edge.db` |

**Data dirs:**
- `~/.myrecall/server/db/edge.db` — frames, embedding_tasks, frames_fts
- `~/.myrecall/server/fts.db` — Legacy SQLStore (some components still use)
- `~/.myrecall/server/frames/` — JPEG snapshots
- `~/.myrecall/server/lancedb/` — Vector embeddings

**Entry:** `python -m openrecall.server`

### Key Data Structures

**Frames Table** (`edge.db`):
```sql
id              INTEGER PRIMARY KEY AUTOINCREMENT
capture_id      TEXT UNIQUE NOT NULL          -- idempotency key
timestamp       TEXT ISO8601 UTC+Z            -- raw UTC (storage only)
local_timestamp TEXT ISO8601 no-offset UTC+8  -- primary query/display time
ingested_at     TEXT ISO8601 UTC+Z
processed_at    TEXT ISO8601 UTC+Z
event_ts        TEXT ISO8601 UTC+Z
app_name        TEXT
window_name     TEXT
browser_url     TEXT
focused         BOOLEAN
device_name     TEXT DEFAULT 'monitor_0'
capture_trigger TEXT                          -- idle/app_switch/manual/click
snapshot_path   TEXT                          -- JPEG path in frames/
image_size_bytes INTEGER
accessibility_text TEXT                       -- AX text (AX-first)
ocr_text        TEXT                          -- OCR fallback
full_text       TEXT                          -- merged, indexed by frames_fts
text_source     TEXT                          -- 'accessibility' | 'ocr'
accessibility_tree_json TEXT
content_hash    TEXT                          -- SHA-256
simhash         INTEGER                       -- text dedup
phash           INTEGER                       -- visual dedup
status          TEXT                          -- pending/processing/completed/failed
description_status TEXT
embedding_status TEXT                         -- NULL/pending/processing/completed/failed
visibility_status TEXT DEFAULT 'pending'      -- pending/queryable/failed
error_message   TEXT
retry_count     INTEGER DEFAULT 0
last_known_app  TEXT
last_known_window TEXT
```

**FTS5:** Single `frames_fts` on `full_text` + metadata. `ocr_text_fts` / `accessibility_fts` were dropped by 2026-03-25 migration.

**Key Architecture Decisions:**
- Host captures/uploads, Edge processes/indexes/searches
- AX-first text extraction; both AX and OCR text preserved independently
- FTS5 + LanceDB vector search with RRF fusion (`hybrid` default)
- qwen3-vl-embedding for multimodal image+text fusion (single embedding per frame)
- `content_type` parameter is deprecated — all searches return merged results

## How to Develop

### Add a Database Field

1. Migration: `openrecall/server/database/migrations/YYYYMMDDHHMMSS_description.sql`
2. Update `FramesStore` in `openrecall/server/database/frames_store.py`
3. Update API in `openrecall/server/api_v1.py`
4. Update tests: `tests/test_p1_s1_frames.py`
5. Run: `pytest tests/test_v3_migrations_bootstrap.py`

### Add a Hot-Reloadable Setting

1. Default in `ClientSettingsStore.DEFAULTS` (`openrecall/client/database/settings_store.py`)
2. Validator in `openrecall/client/web/routes/settings.py` validators dict
3. Getter in `openrecall/client/runtime_config.py` (SQLite > TOML)
4. `notify_config_changed()` after save in settings routes
5. Consumer calls getter on each cycle
6. Test: `tests/test_runtime_config.py`

### Add a Capture Trigger

1. Update `CaptureTrigger` enum in `openrecall/client/events/base.py`
2. Add detection in `openrecall/client/events/`
3. Update `openrecall/client/recorder.py`
4. Test: `tests/test_p1_s2a_trigger_coverage.py`
5. Update: `scripts/acceptance/p1_s2a_local.sh`

### Debug Upload Issues

1. Check spool: `ls ~/.myrecall/client/spool/`
2. Check uploader logs: `[Uploader]` entries
3. Verify Edge: `curl http://localhost:8083/v1/health`
4. Check queue: `curl http://localhost:8083/v1/ingest/queue/status`

## Reference

### Code Structure

```
openrecall/
├── client/            # Host process
│   ├── events/        # macOS CGEventTap capture
│   ├── recorder.py    # Screenshot + AX collection
│   ├── runtime_config.py  # Hot-reload SQLite config
│   ├── spool.py       # Disk queue
│   ├── uploader.py    # Edge upload
│   ├── accessibility/ # macOS AX text extraction
│   ├── chat/          # AI assistant (Pi agent)
│   └── web/           # Flask web UI (port 8889)
├── server/            # Edge process
│   ├── api_v1.py      # v1 API endpoints
│   ├── database/      # SQLite + migrations
│   │   ├── frames_store.py
│   │   ├── embedding_store.py
│   │   └── migrations/
│   ├── search/        # FTS5 + hybrid search
│   ├── processing/    # OCR pipeline
│   ├── description/   # AI description generation
│   └── embedding/     # Vector embedding pipeline
└── shared/            # Settings, models
```

### Testing

```bash
pytest                  # unit + integration (default)
pytest -m unit         # no external deps
pytest -m integration  # requires running Edge server
pytest -m e2e          # end-to-end
pytest -m model        # requires AI models
```

Markers: `unit`, `integration`, `e2e`, `perf`, `security`, `model`, `manual`, `search`.

### API Endpoints

All v1 endpoints defined in `openrecall/server/api_v1.py`. Chat endpoints in `openrecall/client/chat/routes.py`. Legacy `/api/*` returns 410 Gone.

### Environment Variables

All env vars and defaults defined in `openrecall/shared/config.py`. Key ones: `OPENRECALL_SERVER_DATA_DIR`, `OPENRECALL_CLIENT_DATA_DIR`, `OPENRECALL_PORT`, `OPENRECALL_DEBUG`, `OPENRECALL_AI_PROVIDER`, `OPENRECALL_DEVICE`.

### Image Format

Capture/Ingest/Storage/API all use JPEG (`.jpg`/`.jpeg`). Legacy `.webp` support exists only for draining old spool.
