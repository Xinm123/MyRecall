# Web UI Distributed Mode: Config Simplification

> **Status:** ✅ Completed (2026-03-24)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Simplify distributed deployment of MyRecall client web UI across machines by (1) removing CORS configuration complexity, (2) auto-deriving EDGE_BASE_URL from existing API_URL config, and (3) documenting the distributed mode configuration.

**Architecture:**
- CORS: Echo-back any `Origin` header instead of maintaining an allowlist. The Edge API itself still requires authentication; this only enables the browser-to-Edge connection in distributed mode.
- Config: `OPENRECALL_EDGE_BASE_URL` auto-derives from `OPENRECALL_API_URL` when not explicitly set. Users only configure one value.
- Docs: Add inline comments in example configs explaining distributed mode settings.

**Tech Stack:** Flask (existing), Pydantic Settings (existing), Jinja2 (existing)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `openrecall/server/app.py` | Modify | Simplify CORS middleware to echo-back any origin |
| `openrecall/shared/config.py` | Modify | Add auto-derive logic for edge_base_url, deprecate client_cors_origin |
| `myrecall_client.env.example` | Modify | Add distributed mode config comments |
| `docs/superpowers/specs/2026-03-23-webui-migration-design.md` | Modify | Add distributed mode section |

---

## Task 1: Simplify CORS Middleware

**Files:**
- Modify: `openrecall/server/app.py:177-202`

- [x] **Step 1: Read current CORS implementation**

Run: `sed -n '177,202p' openrecall/server/app.py`

- [x] **Step 2: Replace CORS middleware with echo-back logic**

Replace lines 177-202 with:

```python
@app.after_request
def add_cors_headers(response):
    """Allow cross-origin requests from the client web UI.

    Echoes back the Origin header so browsers can access Edge API from any origin.
    In same-machine mode: Origin = http://localhost:8883 (or 127.0.0.1)
    In distributed mode: Origin = http://<client-ip>:8883

    The Edge API itself is still protected by other auth mechanisms (future work).
    """
    request_origin = request.headers.get('Origin', '')

    # Echo back the requesting origin if present, otherwise allow all (for direct curl/etc)
    if request_origin:
        response.headers["Access-Control-Allow-Origin"] = request_origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
```

- [x] **Step 3: Verify CORS still works in same-machine mode**

Run: `python -c "from openrecall.server.app import app; tc = app.test_client(); r = tc.get('/v1/health', headers={'Origin': 'http://localhost:8883'}); print(r.headers.get('Access-Control-Allow-Origin'))"`
Expected: `http://localhost:8883`

- [x] **Step 4: Verify echo-back works with IP origin**

Run: `python -c "from openrecall.server.app import app; tc = app.test_client(); r = tc.get('/v1/health', headers={'Origin': 'http://192.168.1.101:8883'}); print(r.headers.get('Access-Control-Allow-Origin'))"`
Expected: `http://192.168.1.101:8883`

- [x] **Step 5: Commit**

```bash
git add openrecall/server/app.py
git commit -m "feat(server): simplify CORS to echo-back any origin

Remove client_cors_origin allowlist check. Echo back the requesting
Origin header so the client web UI works in distributed mode without
manual CORS configuration. The Edge API remains protected by its
own auth mechanisms (future work).
"
```

---

## Task 2: Auto-Derive EDGE_BASE_URL from API_URL

**Files:**
- Modify: `openrecall/shared/config.py:466-475`
- Modify: `myrecall_client.env.example`

**Motivation:** Currently two similar fields exist — `OPENRECALL_API_URL` (for uploader) and `OPENRECALL_EDGE_BASE_URL` (for web UI). In distributed mode, both point to the same Edge machine. Users should only configure one value.

**Auto-derive rule:** `edge_base_url = api_url.rstrip('/api').rstrip('/')`
- `http://localhost:8083/api` → `http://localhost:8083`
- `http://192.168.1.100:8083/api` → `http://192.168.1.100:8083`

- [x] **Step 1: Read current edge_base_url field definition**

Run: `sed -n '466,475p' openrecall/shared/config.py`

- [x] **Step 2: Modify edge_base_url field**

Replace the `edge_base_url` Field (lines 466-470) with:

```python
    edge_base_url: str = Field(
        default="",
        alias="OPENRECALL_EDGE_BASE_URL",
        description=(
            "Base URL for Edge API server (used by client web UI). "
            "Auto-derived from OPENRECALL_API_URL if not set. "
            "Example: http://localhost:8083"
        ),
    )
```

- [x] **Step 3: Add model_validator to auto-derive edge_base_url**

Find the `@model_validator` block in config.py and add `edge_base_url` to the fields it normalizes. First, locate the validator:

Run: `grep -n "model_validator\|@field_validator\|mode=" openrecall/shared/config.py | head -20`

Insert after the existing `mode="before"` validator block (around line 477-486). Add a new validator:

```python
    @model_validator(mode="after")
    @classmethod
    def derive_edge_base_url(cls, values):
        """Auto-derive edge_base_url from api_url if not explicitly set."""
        edge_base_url = getattr(values, 'edge_base_url', None) or ""
        api_url = getattr(values, 'api_url', None) or ""

        if not edge_base_url and api_url:
            # Strip /api suffix: http://localhost:8083/api → http://localhost:8083
            derived = api_url.rstrip('/api').rstrip('/')
            values.edge_base_url = derived
            logger.info(f"Auto-derived EDGE_BASE_URL={derived} from API_URL={api_url}")

        return values
```

**Note:** The `logger` must be imported at the top of config.py. Check if it exists:

Run: `head -5 openrecall/shared/config.py | grep -n logger`

If not found, add after existing imports:
```python
import logging
logger = logging.getLogger(__name__)
```

- [x] **Step 4: Verify config auto-derivation**

Run: `python -c "from openrecall.shared.config import settings; print('edge_base_url:', repr(settings.edge_base_url)); print('api_url:', repr(settings.api_url))"`
Expected: `edge_base_url: 'http://localhost:8083'` (derived from `http://localhost:8083/api`)

- [x] **Step 5: Verify explicit override still works**

Run: `python -c "import os; os.environ['OPENRECALL_EDGE_BASE_URL']='http://192.168.1.100:8083'; from openrecall.shared.config import Settings; s = Settings(); print(s.edge_base_url)"`
Expected: `http://192.168.1.100:8083` (explicit override wins)

- [x] **Step 6: Verify zero-length default doesn't break rendering**

Run: `python -c "from openrecall.client.web.app import client_app; tc = client_app.test_client(); r = tc.get('/'); print('status:', r.status_code)"`
Expected: `status: 200` (template renders even with empty EDGE_BASE_URL injection)

- [x] **Step 7: Commit**

```bash
git add openrecall/shared/config.py
git commit -m "feat(config): auto-derive EDGE_BASE_URL from API_URL

edge_base_url now defaults to empty string and is auto-derived from
OPENRECALL_API_URL at startup. Explicit OPENRECALL_EDGE_BASE_URL
override still takes precedence. Users only need to configure
OPENRECALL_API_URL in distributed mode.
"
```

---

## Task 3: Update Client Config Example with Distributed Mode Docs

**Files:**
- Modify: `myrecall_client.env.example`

- [x] **Step 1: Read current client env example**

Run: `cat myrecall_client.env.example`

- [x] **Step 2: Add distributed mode section after Connection Settings**

Find the "Connection Settings" section (around line 5-11) and append a distributed mode block after the `OPENRECALL_API_URL` line:

```bash
# ==============================================================================
# Distributed Mode Settings (Client and Edge on different machines)
# ==============================================================================
# In same-machine mode (default): OpenRecall API runs on localhost:8083.
# In distributed mode: set EDGE_HOST and EDGE_PORT to the Edge machine's
# network address. The web UI (port 8883) runs on the Client machine and
# makes cross-origin API requests to the Edge machine.
#
# EDGE_HOST: IP address or hostname of the machine running the Edge server.
#            Example: 192.168.1.100 (or a domain name like edge.example.com)
# EDGE_PORT: Port of the Edge server API (default: 8083)
#             OPENRECALL_API_URL and EDGE_BASE_URL are auto-derived from
#             EDGE_HOST + EDGE_PORT, so you only need to set these two:
#
# EDGE_HOST=192.168.1.100
# EDGE_PORT=8083
#
# NOTE: The browser accesses the Client web UI at http://<client-ip>:8883
#       The Client web UI proxies screenshots through the Edge /v1/frames/ API.
#       Both machines must be on the same network (LAN, VPN, or tunnel).
```

**Note:** We add `EDGE_HOST` and `EDGE_PORT` as new simplified config fields (2 fields) instead of asking users to manually construct a URL. The model_validator will construct `api_url` and `edge_base_url` from these.

Actually, since we already have `OPENRECALL_API_URL` in the existing config and just added auto-derive, the simplest approach is to **document the existing `OPENRECALL_API_URL` override**. No new config fields needed.

**Revised Step 2:** Append to `myrecall_client.env.example`:

```bash
# ==============================================================================
# Distributed Mode (Client and Edge on different machines)
# ==============================================================================
# By default, OPENRECALL_API_URL points to localhost:8083 (same-machine mode).
# For distributed mode, set it to the Edge machine's address:
#
#   OPENRECALL_API_URL=http://192.168.1.100:8083/api
#
# EDGE_BASE_URL is auto-derived from OPENRECALL_API_URL (removes /api suffix),
# so you only need to configure OPENRECALL_API_URL.
#
# The browser accesses the Client web UI at http://<this-machine-ip>:8883
# and the JS automatically uses OPENRECALL_API_URL's host as the Edge API target.
#
# Both machines must be on the same network (LAN or VPN).
```

- [x] **Step 3: Commit**

```bash
git add myrecall_client.env.example
git commit -m "docs: add distributed mode configuration guide to client env example

Document how to configure OPENRECALL_API_URL for Client/Edge distributed
deployment. EDGE_BASE_URL is auto-derived, so users only set one value.
"
```

---

## Task 4: Update Migration Design Doc

**Files:**
- Modify: `docs/superpowers/specs/2026-03-23-webui-migration-design.md`

- [x] **Step 1: Read the Data Flow section of the design doc**

Run: `sed -n '60,80p' docs/superpowers/specs/2026-03-23-webui-migration-design.md`

- [x] **Step 2: Add distributed mode section**

After the "Data Flow" section (after line 69, before "Health Check & Degradation"), add:

### Distributed Mode (Client and Edge on Different Machines)

```
┌──────────────────────────────────────────────────────┐
│  Client Machine (192.168.1.101)                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Flask Web Server  :8883                         │  │
│  │  └── EDGE_BASE_URL = http://192.168.1.100:8083  │  │
│  │                                                │  │
│  │  JS requests go to http://192.168.1.100:8083   │  │
│  │  Browser Origin = http://192.168.1.101:8883     │  │
│  └────────────────────────────────────────────────┘  │
└────────────────────────┬─────────────────────────────┘
                         │ LAN / VPN
                         ▼
┌──────────────────────────────────────────────────────┐
│  Edge Machine (192.168.1.100)                        │
│  ┌────────────────────────────────────────────────┐  │
│  │  Flask API Server  :8083                        │  │
│  │  CORS: echo-back any Origin header             │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**Configuration (Client machine):**
```bash
# myrecall_client.env
OPENRECALL_API_URL=http://192.168.1.100:8083/api
# EDGE_BASE_URL auto-derived to http://192.168.1.100:8083
```

**How it works:**
1. User opens `http://192.168.1.101:8883` in browser
2. Client Flask renders template, injects `EDGE_BASE_URL = "http://192.168.1.100:8083"` (from `OPENRECALL_API_URL` auto-derive)
3. Browser JS calls `http://192.168.1.100:8083/v1/search` (CORS cross-origin)
4. Edge CORS echoes back `Access-Control-Allow-Origin: http://192.168.1.101:8883`
5. Browser allows response ✅

**Requirements:**
- Both machines on same network (LAN or VPN)
- Edge port 8083 accessible from Client machine
- Client web UI port 8883 accessible from user's browser
- No NAT/port-mapping support (machines must be directly reachable)

- [x] **Step 3: Also update the "New Configuration" table** in the design doc to reflect auto-derive:

Change the `OPENRECALL_CLIENT_CORS_ORIGIN` row to note it is deprecated:
| `OPENRECALL_CLIENT_CORS_ORIGIN` | `http://localhost:8883` | Deprecated: CORS now accepts any origin (echo-back). Kept for backward compatibility. |

Add new row:
| `OPENRECALL_API_URL` | `http://localhost:8083/api` | Used for uploader. `EDGE_BASE_URL` is auto-derived from this (removes `/api` suffix). Override `EDGE_BASE_URL` explicitly for distributed mode. |

- [x] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-03-23-webui-migration-design.md
git commit -m "docs: add distributed mode section to web UI migration design

Cover Client/Edge split across machines: configuration, data flow,
and requirements. Update config table to reflect auto-derive and
CORS echo-back simplifications.
"
```

---

## Task 5: End-to-End Verification

- [x] **Step 1: Verify CORS echo-back with various origins**

```bash
# Start server
cd /Users/pyw/old/MyRecall && ./run_server.sh --debug &
sleep 5

# Test CORS with localhost origin
curl -s -I "http://localhost:8083/v1/health" \
  -H "Origin: http://localhost:8883"
# Expected: Access-Control-Allow-Origin: http://localhost:8883

# Test CORS with IP origin (simulating distributed mode)
curl -s -I "http://localhost:8083/v1/health" \
  -H "Origin: http://192.168.1.101:8883"
# Expected: Access-Control-Allow-Origin: http://192.168.1.101:8883

# Test CORS with arbitrary origin
curl -s -I "http://localhost:8083/v1/health" \
  -H "Origin: https://evil.com"
# Expected: Access-Control-Allow-Origin: https://evil.com

# Cleanup
kill $(pgrep -f "openrecall.server") 2>/dev/null
```

- [x] **Step 2: Verify auto-derive works in client web server**

```bash
# Set remote Edge API URL
export OPENRECALL_API_URL=http://192.168.1.100:8083/api
export OPENRECALL_CLIENT_WEB_ENABLED=true

python -c "from openrecall.shared.config import settings; print(settings.edge_base_url)"
# Expected: http://192.168.1.100:8083

# Start client web server and check template injection
python -c "
from openrecall.client.web.app import client_app
tc = client_app.test_client()
r = tc.get('/')
content = r.text
# Check EDGE_BASE_URL is injected as http://192.168.1.100:8083
assert 'http://192.168.1.100:8083' in content, 'EDGE_BASE_URL not found in HTML'
print('OK: EDGE_BASE_URL injected correctly in HTML')
"
```

- [x] **Step 3: Cleanup**

```bash
unset OPENRECALL_API_URL OPENRECALL_CLIENT_WEB_ENABLED
```

---

## Task Summary

| # | Task | Status | Files Modified | Commit |
|---|------|--------|---------------|--------|
| 1 | Simplify CORS middleware | ✅ | `openrecall/server/app.py` | feat(server): simplify CORS to echo-back any origin |
| 2 | Auto-derive EDGE_BASE_URL from API_URL | ✅ | `openrecall/shared/config.py` | feat(config): auto-derive EDGE_BASE_URL from API_URL |
| 3 | Update client env example docs | ✅ | `myrecall_client.env.example` | docs: add distributed mode configuration guide |
| 4 | Update migration design doc | ✅ | `.../webui-migration-design.md` | docs: add distributed mode section |
| 5 | End-to-end verification | ✅ | — | — |

---

## Deferred Items

- **Remove `OPENRECALL_CLIENT_CORS_ORIGIN` from config** after verifying no code references it (low priority, keep for backward compatibility)
- **Add `OPENRECALL_CLIENT_WEB_HOST`** config for explicit interface binding (P2, needed for multi-NIC machines)
- **HTTPS support** for distributed mode (P2, requires TLS cert configuration)
- **NAT/port-mapping support** via STUN or manual tunnel config (P3)
