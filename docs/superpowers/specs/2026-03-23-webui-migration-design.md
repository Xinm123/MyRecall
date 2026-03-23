# Web UI Migration: Server → Client

**Date:** 2026-03-23
**Status:** Approved
**Reference:** Aligns with screenpipe's "server as pure API" philosophy

## Context

MyRecall v3 uses a Host/Edge split architecture. The Web UI (Jinja2 templates) is currently hosted on the Edge Server (Flask on port 8083), alongside the API. The Client only handles capture → spool → upload.

This design migrates the Web UI to the Client, aligning with screenpipe's architecture where the server is a pure API and the frontend connects directly to it.

## Decision

Move Web UI templates from Edge Server to Client. The Client provides an independent Flask web server on port 5000. API calls from the browser go directly to Edge (port 8083) via CORS.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Client (Host)           :5000                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Flask Web Server                              │  │
│  │  ├── GET /           → render index.html       │  │
│  │  ├── GET /search     → render search.html      │  │
│  │  ├── GET /timeline   → render timeline.html    │  │
│  │  └── GET /vendor/*   → static vendor files     │  │
│  │                                                │  │
│  │  Config injection: EDGE_BASE_URL passed to     │  │
│  │  render_template()                             │  │
│  └────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────┘
                             │ Browser direct fetch
                             ▼
┌──────────────────────────────────────────────────────┐
│  Edge Server           :8083                         │
│  ┌────────────────────────────────────────────────┐  │
│  │  Flask API Server (pure API, no HTML)          │  │
│  │  ├── GET/POST /v1/*  (FTS5 search, frames)   │  │
│  │  ├── GET /api/*     (config, legacy)         │  │
│  │  └── GET /v1/health                           │  │
│  │  + CORS headers (Access-Control-Allow-Origin)  │  │
│  └────────────────────────────────────────────────┘  │
│  └── ~/MRS/  (frames/, db/, fts.db)               │
└──────────────────────────────────────────────────────┘
```

### Alignment with screenpipe

| Aspect | Screenpipe | MyRecall v3 (after) |
|--------|------------|---------------------|
| Server | Pure API | Pure API |
| UI Provider | Tauri (static files) | Client Flask (Jinja2) |
| Frontend → API | Browser → :3030 direct | Browser → :8083 direct |
| CORS | Permissive | Configured for :5000 |
| Process Model | Single-process monolith | Dual-process (Host + Edge) |

MyRecall retains Host/Edge separation, so CORS is needed for cross-origin requests.

## Data Flow

1. User opens `http://localhost:5000`
2. Client Flask renders template, injecting `EDGE_BASE_URL = "http://localhost:8083"`
3. Browser receives HTML, JS calls `EDGE_BASE_URL + '/v1/search'` (CORS cross-origin)
4. Edge returns JSON, JS renders the page

### Health Check & Degradation

JS polls Edge health regularly. If Edge is offline, a warning banner appears — the page does not crash.

## Directory Structure

```
openrecall/
├── client/
│   ├── web/                          # NEW
│   │   ├── __init__.py
│   │   ├── app.py                    # Flask web server (~60 lines)
│   │   ├── templates/                # Copied from server/templates/
│   │   │   ├── index.html
│   │   │   ├── search.html
│   │   │   ├── timeline.html
│   │   │   ├── layout.html
│   │   │   └── icons.html
│   │   └── vendor/                   # Copied from server/vendor/
│   │       └── alpine.min.js
│   ├── __main__.py                   # MODIFIED: start web server
│   └── ...
└── server/
    ├── app.py                        # MODIFIED: add CORS middleware
    ├── templates/                     # Keep for now (future removal)
    └── ...
```

## New Configuration

Added to `openrecall/shared/config.py`:

| Config Key | Default | Description |
|------------|---------|-------------|
| `OPENRECALL_CLIENT_WEB_PORT` | `5000` | Client web server port |
| `OPENRECALL_CLIENT_WEB_ENABLED` | `true` | Enable client web server |
| `OPENRECALL_EDGE_BASE_URL` | `http://localhost:8083` | Edge API base URL |
| `OPENRECALL_CLIENT_CORS_ORIGIN` | `http://localhost:5000` | CORS allowed origin for Edge |

## Template Changes

All `fetch()` calls and URL references in templates are prefixed with `EDGE_BASE_URL` (injected at render time). ~12 locations across 4 files:

| File | Changes |
|------|---------|
| `layout.html` | health check, config API (~3) |
| `index.html` | memories API, frames URL (~5) |
| `search.html` | search API, frames URL (~2) |
| `timeline.html` | frames URL (~2) |

## Startup Behavior

- Client's web server starts **independently** of Edge (no wait for Edge)
- Edge availability is detected by JS via health polling
- `--no-web` flag on client disables web server (headless mode)

```
# Terminal 1
./run_server.sh --debug

# Terminal 2
./run_client.sh              # With web UI (default)
./run_client.sh --no-web     # Headless
```

## Implementation Steps

1. Add config fields to `openrecall/shared/config.py`
2. Create `openrecall/client/web/` directory structure
3. Copy templates from `server/templates/` to `client/web/templates/`
4. Copy `alpine.min.js` to `client/web/vendor/`
5. Write `openrecall/client/web/app.py` (~60 lines)
6. Modify `openrecall/client/__main__.py` to start web server
7. Add CORS middleware to `openrecall/server/app.py`
8. Update ~12 locations in templates to use `EDGE_BASE_URL`
9. Add `--no-web` flag parsing to client entry point
10. Update `run_client.sh` to support `--no-web`

## Future Work

- Remove templates from `openrecall/server/templates/` after migration verified
- Consider removing server web routes from `openrecall/server/app.py`
