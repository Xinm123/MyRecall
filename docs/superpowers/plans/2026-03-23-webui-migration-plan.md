# Web UI Migration: Server → Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Web UI templates from Edge Server to Client. Client runs a Flask web server on port 5000 serving Jinja2 templates. API calls from templates go directly to Edge (port 8083) via CORS.

**Architecture:** Direct Connect mode — Client Flask serves HTML only, browser fetches API from Edge directly (per screenpipe alignment). No proxy layer needed.

**Tech Stack:** Flask (existing), Jinja2 (existing), Pydantic Settings (existing)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `openrecall/shared/config.py` | Modify | Add 4 new config fields |
| `openrecall/server/app.py` | Modify | Add CORS middleware |
| `openrecall/client/__main__.py` | Modify | Parse `--no-web`, start web server |
| `openrecall/client/web/__init__.py` | Create | Package marker |
| `openrecall/client/web/app.py` | Create | Flask web server (~60 lines) |
| `openrecall/client/web/templates/*.html` | Create | Copy from server/templates/ |
| `openrecall/client/web/vendor/alpine.min.js` | Create | Copy from server/vendor/ |
| Template files (4 files) | Modify | ~12 EDGE_BASE_URL injections |
| `run_client.sh` | Modify | Support `--no-web` flag |

---

## Phase 1: Config & Infrastructure

### Task 1: Add config fields

**Files:**
- Modify: `openrecall/shared/config.py:368` (after the `disable_similarity_filter` field)

- [ ] **Step 1: Add the four new config fields**

Insert after line 422 (after the `fusion_log_enabled` field):

```python
    # Client Web UI Configuration
    client_web_port: int = Field(
        default=5000,
        alias="OPENRECALL_CLIENT_WEB_PORT",
        description="Port for client web UI server",
    )
    client_web_enabled: bool = Field(
        default=True,
        alias="OPENRECALL_CLIENT_WEB_ENABLED",
        description="Enable client web UI server",
    )
    edge_base_url: str = Field(
        default="http://localhost:8083",
        alias="OPENRECALL_EDGE_BASE_URL",
        description="Base URL for Edge API server (used by client web UI)",
    )
    client_cors_origin: str = Field(
        default="http://localhost:5000",
        alias="OPENRECALL_CLIENT_CORS_ORIGIN",
        description="Allowed CORS origin for Edge server (client web UI origin)",
    )
```

- [ ] **Step 2: Verify config loads correctly**

Run: `python -c "from openrecall.shared.config import settings; print(settings.client_web_port, settings.edge_base_url, settings.client_cors_origin, settings.client_web_enabled)"`
Expected: `5000 http://localhost:8083 http://localhost:5000 True`

- [ ] **Step 3: Commit**

```bash
git add openrecall/shared/config.py
git commit -m "feat(config): add client web UI config fields

Add OPENRECALL_CLIENT_WEB_PORT, OPENRECALL_CLIENT_WEB_ENABLED,
OPENRECALL_EDGE_BASE_URL, OPENRECALL_CLIENT_CORS_ORIGIN settings.
```

---

### Task 2: Add CORS middleware to Edge

**Files:**
- Modify: `openrecall/server/app.py` (after line 163, after `init_background_worker` function)

- [ ] **Step 1: Add CORS after_request handler**

Add at the end of `app.py`, after the `init_background_worker` function:

```python
@app.after_request
def add_cors_headers(response):
    """Allow cross-origin requests from the client web UI."""
    response.headers["Access-Control-Allow-Origin"] = settings.client_cors_origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response
```

- [ ] **Step 2: Verify it works**

Run: `python -c "from openrecall.server.app import app; print('CORS middleware added')"`
Expected: Output without import errors

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/app.py
git commit -m "feat(server): add CORS headers for client web UI origin"
```

---

## Phase 2: Client Web Server

### Task 3: Create client web package

**Files:**
- Create: `openrecall/client/web/__init__.py`
- Create: `openrecall/client/web/app.py`
- Create: `openrecall/client/web/templates/` (directory)
- Create: `openrecall/client/web/vendor/` (directory)

- [ ] **Step 1: Create `__init__.py`**

```python
"""Client web UI package."""

from openrecall.client.web.app import start_web_server

__all__ = ["start_web_server"]
```

- [ ] **Step 2: Create `app.py`**

```python
"""Flask web server for client-side Web UI."""

import logging
import threading
from flask import Flask, render_template, send_from_directory
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

client_app = Flask(__name__, template_folder="templates")


@client_app.context_processor
def inject_edge_base_url():
    """Make EDGE_BASE_URL available to all templates."""
    return {"EDGE_BASE_URL": settings.edge_base_url}


@client_app.route("/")
def index():
    return render_template("index.html")


@client_app.route("/search")
def search():
    return render_template("search.html")


@client_app.route("/timeline")
def timeline():
    return render_template("timeline.html")


@client_app.route("/vendor/<path:filename>")
def vendor(filename):
    return send_from_directory("vendor", filename)


def start_web_server():
    """Start the web server in a daemon thread and return the thread."""
    t = threading.Thread(
        target=lambda: client_app.run(
            host="0.0.0.0",
            port=settings.client_web_port,
            debug=settings.debug,
            use_reloader=False,
        ),
        daemon=True,
        name="client-web-server",
    )
    t.start()
    logger.info(f"Web UI started: http://localhost:{settings.client_web_port}")
    return t
```

- [ ] **Step 3: Verify imports work**

Run: `python -c "from openrecall.client.web.app import client_app, start_web_server; print('OK')"`
Expected: `OK` (may warn about missing templates — that's expected before Task 4)

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/__init__.py openrecall/client/web/app.py
git commit -m "feat(client): add web UI Flask app on port 5000"
```

---

### Task 4: Copy templates and static assets

**Files:**
- Create: `openrecall/client/web/templates/index.html` (copy from server)
- Create: `openrecall/client/web/templates/search.html` (copy from server)
- Create: `openrecall/client/web/templates/timeline.html` (copy from server)
- Create: `openrecall/client/web/templates/layout.html` (copy from server)
- Create: `openrecall/client/web/templates/icons.html` (copy from server)
- Create: `openrecall/client/web/vendor/alpine.min.js` (copy from server)

- [ ] **Step 1: Copy all template files**

```bash
cp openrecall/server/templates/index.html openrecall/client/web/templates/
cp openrecall/server/templates/search.html openrecall/client/web/templates/
cp openrecall/server/templates/timeline.html openrecall/client/web/templates/
cp openrecall/server/templates/layout.html openrecall/client/web/templates/
cp openrecall/server/templates/icons.html openrecall/client/web/templates/
cp openrecall/server/vendor/alpine.min.js openrecall/client/web/vendor/
```

- [ ] **Step 2: Verify files exist**

Run: `ls openrecall/client/web/templates/ && ls openrecall/client/web/vendor/`
Expected: 5 HTML files + alpine.min.js

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/ openrecall/client/web/vendor/
git commit -m "feat(client): copy web UI templates and vendor assets"
```

---

## Phase 3: Template Modifications

### Task 5: Update layout.html

**Files:**
- Modify: `openrecall/client/web/templates/layout.html`

First, read `layout.html` and identify all fetch() calls and hardcoded URLs that need `EDGE_BASE_URL` prefix.

- [ ] **Step 1: Read layout.html to find all API calls**

Run: `grep -n "fetch\|/api\|/v1\|/screenshots" openrecall/client/web/templates/layout.html`

Expected locations (exact lines may vary):
- Health check polling: `fetch('/v1/health')`
- Config GET: `fetch('/api/config')`
- Config POST: `fetch('/api/config', {`

These should become `fetch(EDGE_BASE_URL + '/v1/health')` etc.

- [ ] **Step 2: Apply EDGE_BASE_URL prefix to all API calls in layout.html**

For each `fetch('/...')` or `fetch("/...")`, change to `fetch(EDGE_BASE_URL + '/...')`.

- [ ] **Step 3: Verify all changed**

Run: `grep -n "fetch\|/api\|/v1" openrecall/client/web/templates/layout.html | grep -v "EDGE_BASE_URL"`
Expected: No results (all API calls should use EDGE_BASE_URL)

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/layout.html
git commit -m "feat(templates): add EDGE_BASE_URL prefix to API calls in layout.html"
```

---

### Task 6: Update index.html

**Files:**
- Modify: `openrecall/client/web/templates/index.html`

- [ ] **Step 1: Read index.html to find all API calls and frame URLs**

Run: `grep -n "fetch\|/api\|/v1\|/screenshots" openrecall/client/web/templates/index.html`

Expected locations:
- Memories API: `fetch('/api/memories/latest?...')` and `fetch('/api/memories/recent?...')`
- Frame URLs: `/v1/frames/${frameId}` and `/v1/frames/${frameId}/ocr-vis`

- [ ] **Step 2: Apply EDGE_BASE_URL prefix**

For each API endpoint, change:
- `'/api/...'` → `EDGE_BASE_URL + '/api/...'`
- `'/v1/...'` → `EDGE_BASE_URL + '/v1/...'`

- [ ] **Step 3: Verify all changed**

Run: `grep -n "fetch\|/api\|/v1" openrecall/client/web/templates/index.html | grep -v "EDGE_BASE_URL"`
Expected: No results (all API calls should use EDGE_BASE_URL)

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(templates): add EDGE_BASE_URL prefix to API calls in index.html"
```

---

### Task 7: Update search.html

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

- [ ] **Step 1: Read search.html to find all API calls and frame URLs**

Run: `grep -n "fetch\|/api\|/v1\|/screenshots" openrecall/client/web/templates/search.html`

Expected locations:
- Search API: `fetch('/v1/search?...')`
- Frame URL: `/v1/frames/${frameId}`

- [ ] **Step 2: Apply EDGE_BASE_URL prefix**

- [ ] **Step 3: Verify all changed**

Run: `grep -n "fetch\|/api\|/v1" openrecall/client/web/templates/search.html | grep -v "EDGE_BASE_URL"`
Expected: No results

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(templates): add EDGE_BASE_URL prefix to API calls in search.html"
```

---

### Task 8: Update timeline.html

**Files:**
- Modify: `openrecall/client/web/templates/timeline.html`

- [ ] **Step 1: Read timeline.html to find all API calls and frame URLs**

Run: `grep -n "fetch\|/api\|/v1\|/screenshots" openrecall/client/web/templates/timeline.html`

Expected locations:
- Frame URLs: `/v1/frames/${frameId}`

- [ ] **Step 2: Apply EDGE_BASE_URL prefix**

- [ ] **Step 3: Verify all changed**

Run: `grep -n "fetch\|/api\|/v1" openrecall/client/web/templates/timeline.html | grep -v "EDGE_BASE_URL"`
Expected: No results

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/timeline.html
git commit -m "feat(templates): add EDGE_BASE_URL prefix to API calls in timeline.html"
```

---

## Phase 4: Client Entry Point Integration

### Task 9: Integrate web server into client entry point

**Files:**
- Modify: `openrecall/client/__main__.py`

- [ ] **Step 1: Modify `main()` to start web server when enabled**

Add at the beginning of `main()`, after the logger config block:

```python
    # Start client web UI server (if enabled)
    web_server_thread = None
    if settings.client_web_enabled:
        from openrecall.client.web.app import start_web_server
        web_server_thread = start_web_server()
```

- [ ] **Step 2: Handle --no-web flag**

At the top of `__main__.py` (before `from openrecall.shared.config import settings`), add:

```python
import sys

# Parse --no-web flag before config loads
if "--no-web" in sys.argv:
    sys.argv.remove("--no-web")
    import os
    os.environ["OPENRECALL_CLIENT_WEB_ENABLED"] = "false"
```

- [ ] **Step 3: Verify it works**

Run: `python -m openrecall.client --no-web 2>&1 | head -20`
Expected: No "Web UI started" log line when `--no-web` is passed

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/__main__.py
git commit -m "feat(client): start web UI server on client startup"
```

---

## Phase 5: Run Scripts

### Task 10: Update run_client.sh

**Files:**
- Modify: `run_client.sh` (or `scripts/run_client.sh` — check location first)

- [ ] **Step 1: Find run_client.sh**

Run: `find . -name "run_client.sh" -o -name "run*.sh" 2>/dev/null | head -10`
Expected: Script path

- [ ] **Step 2: Update to support --no-web**

If `--no-web` flag is detected, pass it through:

```bash
# Pass --no-web flag to python
python -m openrecall.client "$@"
```

The `--no-web` parsing in `__main__.py` handles the rest.

- [ ] **Step 3: Test with --no-web**

```bash
./run_client.sh --no-web &
sleep 2
# Should NOT see "Web UI started" in logs
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add run_client.sh  # or the correct path
git commit -m "chore: run_client.sh passes --no-web to client"
```

---

## Phase 6: Verification

### Task 11: End-to-end verification

- [ ] **Step 1: Start Edge server**

```bash
./run_server.sh --debug &
sleep 5
```

- [ ] **Step 2: Start Client**

```bash
./run_client.sh --debug &
sleep 3
```

- [ ] **Step 3: Test all three pages load**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/search
# Expected: 200

curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/timeline
# Expected: 200
```

- [ ] **Step 4: Verify CORS headers on Edge**

```bash
curl -s -I -X OPTIONS http://localhost:8083/v1/health \
  -H "Origin: http://localhost:5000" \
  -H "Access-Control-Request-Method: GET"
# Expected: Access-Control-Allow-Origin: http://localhost:5000
```

- [ ] **Step 5: Cleanup**

```bash
kill $(pgrep -f "openrecall.client") $(pgrep -f "openrecall.server") 2>/dev/null
```

---

## Task Summary

| # | Task | Files Modified | Commit |
|---|------|---------------|--------|
| 1 | Config fields | `openrecall/shared/config.py` | feat(config): add client web UI config fields |
| 2 | CORS middleware | `openrecall/server/app.py` | feat(server): add CORS headers |
| 3 | Client web package | `openrecall/client/web/__init__.py`, `app.py` | feat(client): add web UI Flask app |
| 4 | Copy templates | `openrecall/client/web/templates/`, `vendor/` | feat(client): copy web UI templates |
| 5 | layout.html | `openrecall/client/web/templates/layout.html` | feat(templates): layout.html |
| 6 | index.html | `openrecall/client/web/templates/index.html` | feat(templates): index.html |
| 7 | search.html | `openrecall/client/web/templates/search.html` | feat(templates): search.html |
| 8 | timeline.html | `openrecall/client/web/templates/timeline.html` | feat(templates): timeline.html |
| 9 | Client integration | `openrecall/client/__main__.py` | feat(client): start web UI on startup |
| 10 | Run script | `run_client.sh` | chore: run_client.sh --no-web |
| 11 | E2E verification | — | — |
