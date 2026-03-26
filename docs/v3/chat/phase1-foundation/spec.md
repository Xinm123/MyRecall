# Phase 1: Foundation - Specification

## Overview

Phase 1 establishes the infrastructure for Pi integration, enabling MyRecall to launch and communicate with the Pi coding agent for chat functionality.

## Goals

1. Install and manage Pi as a subprocess
2. Configure LLM providers for Pi
3. Create the `myrecall-search` skill for tool usage
4. Validate integration through testing

## Non-Goals

- SSE streaming implementation (Phase 2)
- Web UI for chat (Phase 3)
- Interactive login command
- Ollama local model support

## Decisions Summary

| Decision | Choice |
|----------|--------|
| Provider support | A3: Pi built-in providers — `minimax-cn` (default) + `kimi-coding` (backup) |
| Config location | Reuse `~/.pi/agent/` |
| API Key priority | Environment variables (`MINIMAX_CN_API_KEY` / `KIMI_API_KEY`) > auth.json |
| Model list | Reference Pi's built-in models only |
| Default model | MiniMax-M2.7 |
| Config integration | Independent from existing MyRecall AI config |
| JSON Mode | Basic validation in Phase 1, full implementation in Phase 2 |
| Config write | Only write `auth.json`, not `models.json` (Pi provides built-in models) |

**Why `minimax-cn` as default?**
- Pi bundles `minimax-cn` natively — no custom `models.json` needed
- `minimax-cn` provider: `https://api.minimaxi.com/anthropic`, `anthropic-messages` API
- Multiple model tiers: M2, M2.1, M2.5, M2.7 (each with `-highspeed` variant)
- 204K context window, reasoning-capable, cost-effective
- `kimi-coding` available as free backup (requires `KIMI_API_KEY`)

## Components

### 1. Pi Manager

**File**: `openrecall/client/chat/pi_manager.py`

**Responsibilities**:
- Find bun executable
- Find Pi executable (cli.js entrypoint)
- Install Pi to `~/.myrecall/pi-agent/`
- Verify Pi installation and version

**Key Functions**:

```python
def find_bun_executable() -> Optional[str]:
    """Locate bun executable on the system."""

def find_pi_executable() -> Optional[str]:
    """Locate Pi CLI entrypoint (cli.js)."""

def ensure_installed() -> bool:
    """Install Pi if not present or version mismatch."""

def is_version_current() -> bool:
    """Check if installed Pi matches expected version."""
```

**Constants**:

```python
PI_PACKAGE = "@mariozechner/pi-coding-agent@0.60.0"
PI_INSTALL_DIR = Path.home() / ".myrecall" / "pi-agent"
```

### 2. Config Manager

**File**: `openrecall/client/chat/config_manager.py`

**Responsibilities**:
- Read API key for a given provider (diagnostic/informational use)
- Provide default provider and model constants
- **Phase 1: ConfigManager does NOT write auth.json or models.json**
  - Pi manages its own credentials via `~/.pi/agent/auth.json`
  - Users configure via environment variables or manual file editing
  - Pi reads credentials directly from env vars or auth.json

**Key Functions**:

```python
def get_api_key(provider: str) -> Optional[str]:
    """
    Read API key for a given provider.

    This is for informational/diagnostic purposes only.
    Pi reads credentials directly from:
      1. CLI --api-key flag (highest priority)
      2. auth.json (recommended for persistence)
      3. Environment variable (e.g. MINIMAX_CN_API_KEY)

    Pi's auth.json priority is HIGHER than environment variables.
    """

def get_default_provider() -> str:
    """Return default provider name: 'minimax-cn'."""

def get_default_model() -> str:
    """Return default model ID: 'MiniMax-M2.7'."""
```

**Config Paths** (reference only, read access):

```python
PI_CONFIG_DIR = Path.home() / ".pi" / "agent"
AUTH_JSON = PI_CONFIG_DIR / "auth.json"
# Note: models.json is NOT used in Phase 1 — Pi provides built-in minimax-cn + kimi-coding
```

**Provider → Env Var Mapping** (Pi native providers):

| Provider | Env Var | auth.json key | Notes |
|----------|---------|---------------|-------|
| `minimax-cn` | `MINIMAX_CN_API_KEY` | `minimax-cn` | **Default for MVP** |
| `kimi-coding` | `KIMI_API_KEY` | `kimi-coding` | Free backup |
| `anthropic` | `ANTHROPIC_API_KEY` | `anthropic` | Future expansion |
| `openai` | `OPENAI_API_KEY` | `openai` | Future expansion |
| `custom` | `CUSTOM_API_KEY` | `custom` | Via models.json |

### 3. Skill: myrecall-search

**File**: `openrecall/client/chat/skills/myrecall-search/SKILL.md`

**Purpose**: Teach Pi how to use MyRecall's API endpoints for search and retrieval.

**Tool Surface (MVP)**:

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/activity-summary` | Broad overview of screen activity |
| `GET /v1/search` | Search screen content by text/metadata |
| `GET /v1/frames/{id}/context` | Detailed frame context (text, nodes, URLs) |
| `GET /v1/frames/{id}` | Retrieve frame image (PNG/JPEG) |

**Skill Loading**:

Pi discovers skills from specific directories. PiManager ensures the skill is
available at the correct location for Pi to discover:

```
Source:   openrecall/client/chat/skills/myrecall-search/SKILL.md
Target:   ~/.pi/agent/skills/myrecall-search/SKILL.md
Install:  pi_manager.ensure_skill_installed() (called from ensure_installed())
Update:   Always copy from source (overwrite) to pick up changes
```

Installation is done by `PiManager.ensure_skill_installed()` — it copies the
skill file to `~/.pi/agent/skills/` on every `ensure_installed()` call, so
changes to the source file are picked up on next MyRecall startup.

**Skill Structure**:

```markdown
---
name: myrecall-search
description: Query the user's screen history via MyRecall API...
---

# MyRecall API

Local REST API at `http://localhost:8083`.

## Context Window Protection
[Rules for managing context size]

## 1. Activity Summary — GET /v1/activity-summary
[API documentation]

## 2. Search — GET /v1/search
[API documentation]

## 3. Frame Context — GET /v1/frames/{id}/context
[API documentation]

## 4. Frame Image — GET /v1/frames/{id}
[API documentation]

## Agent Policy
[Strategy for using tools effectively]
```

### 4. Model Definitions

**File**: `openrecall/client/chat/models.py`

**Purpose**: Define default provider and model constants only. These are the **only** model-related values MyRecall needs — all model metadata (context windows, cost, capabilities) is maintained by Pi internally in `models.generated.ts` and is not duplicated by MyRecall.

**Why no model metadata dictionary?** Pi is the authoritative source for all built-in model information. The `minimax-cn` and `kimi-coding` providers are built into the Pi release with their complete metadata (base URLs, context windows, cost tiers, reasoning capabilities, etc.). Maintaining a separate copy would create a sync risk with no functional benefit in Phase 1. Phase 4 Config UI should source model data from Pi directly (e.g., by parsing Pi's TypeScript definitions or calling `pi --list-models`).

```python
DEFAULT_PROVIDER = "minimax-cn"
DEFAULT_MODEL = "MiniMax-M2.7"
```

**Available providers** (from Pi built-ins):

| Provider | Env Var | Default Model | Notes |
|----------|---------|---------------|-------|
| `minimax-cn` | `MINIMAX_CN_API_KEY` | `MiniMax-M2.7` | **Default** — China endpoint |
| `kimi-coding` | `KIMI_API_KEY` | `k2p5` | Free (Moonshot sponsored) |

## Directory Structure

```
openrecall/client/chat/
├── __init__.py
├── pi_manager.py           # Pi installation management
├── config_manager.py       # Provider/API key configuration
├── models.py               # Default provider/model constants only
└── skills/
    └── myrecall-search/
        └── SKILL.md        # MyRecall API skill

~/.myrecall/
└── pi-agent/               # Pi installation
    ├── node_modules/
    │   └── @mariozechner/
    │       └── pi-coding-agent/
    └── package.json

~/.pi/agent/                # Pi configuration (shared with Pi)
├── auth.json               # API keys only (mode 0o600)
└── settings.json           # Global settings
# Note: models.json is NOT written by MyRecall — Pi provides built-in kimi-coding models
```

## API Key Resolution

### How Pi Reads Credentials (Reference)

Pi resolves API keys in this order:

```
1. CLI --api-key flag      (highest priority)
2. auth.json file          (recommended for persistence)
3. Environment variable     (e.g. MINIMAX_CN_API_KEY)

Note: auth.json takes priority over environment variables.
If both are set, Pi uses the value from auth.json.
```

### How ConfigManager Reads Keys (Phase 1)

For informational/diagnostic purposes, ConfigManager reads keys with a simplified priority:

```
1. Environment variable (e.g. MINIMAX_CN_API_KEY, KIMI_API_KEY)
2. auth.json file
```

This is a **read-only** operation — it does not change Pi's actual behavior.

### User Configuration (Phase 1 MVP)

Phase 1 is MVP with **no interactive login command**. Users configure credentials manually:

```bash
# Option 1: Environment variable (recommended for quick setup)
export MINIMAX_CN_API_KEY=your_key_here

# Option 2: Manual auth.json editing
# Edit ~/.pi/agent/auth.json:
# {"minimax-cn": {"type": "api_key", "key": "your_key_here"}}

# Option 3: Use kimi-coding (free, no API key needed)
# Just ensure KIMI_API_KEY is not set, Pi will use kimi-coding
```

**See also**: Screenpipe's approach — it writes to auth.json AND sets env vars on the Pi subprocess. This is more complex than needed for Phase 1. We defer credential management UI to Phase 4.

## Installation Flow

```
ensure_installed()
    │
    ├─→ Check if Pi already installed
    │       │
    │       ├─→ Yes: Check version
    │       │       │
    │       │       ├─→ Version matches: Skip
    │       │       └─→ Version mismatch: Reinstall
    │       │
    │       └─→ No: Install fresh
    │
    ├─→ Find bun executable
    │
    ├─→ Create ~/.myrecall/pi-agent/
    │
    ├─→ Seed package.json (with overrides)
    │
    └─→ bun add @mariozechner/pi-coding-agent@0.60.0 @anthropic-ai/sdk
```

## Configuration Flow (A3: minimax-cn default, kimi-coding backup)

```
validate_pi_config(provider, model, api_key)
    │
    │  A3: Pi provides built-in providers — no models.json write needed
    │
    └─► Phase 1: No-op (read-only)
        - ConfigManager.get_api_key() reads from env var or auth.json
        - Pi resolves credentials from env vars or ~/.pi/agent/auth.json
        - Users configure via environment variables (MINIMAX_CN_API_KEY, KIMI_API_KEY)

        Phase 4+: Writing auth.json (Config UI)
        - validate_pi_config() merges credentials into ~/.pi/agent/auth.json
        - Atomic write: temp file + rename
        - Permissions: 0o600
        - Always merge-preserve other providers' keys
```

## Acceptance Criteria

- [ ] `find_bun_executable()` returns valid bun path or None
- [ ] `ensure_installed()` installs Pi to `~/.myrecall/pi-agent/`
- [ ] `find_pi_executable()` returns cli.js path after installation
- [ ] `get_api_key()` resolves from environment variable first
- [ ] `validate_pi_config()` is defined as a no-op stub (does not write auth.json in Phase 1)
- [ ] `validate_pi_config()` interface is documented with Phase 4 merge-preserve semantics
- [ ] `myrecall-search/SKILL.md` documents all MVP endpoints
- [ ] SKILL.md documents `content_type` parameter as deprecated and ignored
- [ ] Integration test passes: Pi can call `/v1/activity-summary`

## Dependencies

- **bun**: JavaScript runtime (must be installed by user)
- **Pi**: `@mariozechner/pi-coding-agent@0.60.0`
- **MyRecall Edge Server**: Running on `localhost:8083` for testing

## References

- **Pi minimax-cn Provider**: `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4620, `minimax-cn` provider)
- **Pi minimax Provider (international)**: `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4500, `minimax` provider)
- **Pi kimi-coding Provider**: `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4464, `kimi-coding` provider)
- **Pi Providers Docs**: `_ref/pi-mono/packages/coding-agent/docs/providers.md`
- **Pi Models Docs**: `_ref/pi-mono/packages/coding-agent/docs/models.md`
- **Pi README**: `_ref/pi-mono/packages/coding-agent/README.md`
- **Pi Skills Docs**: `_ref/pi-mono/packages/coding-agent/docs/skills.md`
- **Screenpipe Pi Executor**: `_ref/screenpipe/crates/screenpipe-core/src/agents/pi.rs`

## Risks

| Risk | Mitigation |
|------|------------|
| bun not installed | Clear error message with installation link |
| Pi version incompatibility | Pin version, test before upgrade |
| Config file corruption | Atomic writes, backup before modify |
| API key exposure | File permissions 0o600, no logging |
| `MINIMAX_CN_API_KEY` not set | Clear error message with setup instructions |
| `minimax-cn` provider unavailable | Fallback message suggesting `kimi-coding` (free) |
| Pi version upgrade strategy | Pin version in `PI_PACKAGE`; review Pi release notes before upgrading; run integration tests before merging version bump |

