# Phase 1: Foundation - Implementation Plan

## Overview

This plan outlines the implementation steps for Phase 1, establishing Pi integration infrastructure for MyRecall chat functionality.

## Prerequisites

- [x] MyRecall Edge server running on `localhost:8083`
- [x] API endpoints implemented: `/v1/activity-summary`, `/v1/search`, `/v1/frames/{id}/context`, `/v1/frames/{id}`
- [x] bun installed on development machine

## Task Breakdown

### Task 1.1: Pi Manager Module

**File**: `openrecall/client/chat/pi_manager.py`

**Estimated effort**: Medium

**Steps**:

1. Create `openrecall/client/chat/` directory structure
2. Implement `find_bun_executable()`
   - Check bundled bun (next to executable)
   - Check common paths: `~/.bun/bin/bun`, `/opt/homebrew/bin/bun`, `/usr/local/bin/bun`
   - Fallback to `which bun` / `where bun`
   - If bun not found: raise `PiInstallError` with a clear message including the installation URL (e.g. https://bun.sh)
3. Implement `find_pi_executable()`
   - Check `~/.myrecall/pi-agent/node_modules/@mariozechner/pi-coding-agent/dist/cli.js`
   - Check global install locations
   - Fallback to `which pi` / `where pi`
4. Implement `is_version_current()`
   - Read `package.json` from installed Pi
   - Compare version with `PI_PACKAGE`
5. Implement `ensure_installed()`
   - Check existing installation
   - Create install directory
   - Seed `package.json` with overrides (lru-cache fix for Windows)
   - Run `bun add @mariozechner/pi-coding-agent@0.60.0 @anthropic-ai/sdk`
   - Call `ensure_skill_installed()` to copy skill to Pi skills directory
6. Implement `ensure_skill_installed()`
   - Create `~/.pi/agent/skills/` directory if needed
   - Copy skill file from `openrecall/client/chat/skills/myrecall-search/SKILL.md`
     to `~/.pi/agent/skills/myrecall-search/SKILL.md`
   - Always overwrite to pick up changes
7. Add logging and error handling
8. Write unit tests

**Deliverables**:
- `openrecall/client/chat/__init__.py`
- `openrecall/client/chat/pi_manager.py`
- `tests/test_chat_pi_manager.py`

**Validation**:
```bash
python -c "from openrecall.client.chat.pi_manager import ensure_installed; ensure_installed()"
# Verify: ls ~/.myrecall/pi-agent/node_modules/@mariozechner/pi-coding-agent/
# Verify skill: cat ~/.pi/agent/skills/myrecall-search/SKILL.md
```

---

### Task 1.2: Config Manager Module

**File**: `openrecall/client/chat/config_manager.py`

**Estimated effort**: Small (read-only in Phase 1)

**Steps**:

1. Define config paths and constants
2. Define `validate_pi_config(provider, model, api_key)` as a no-op stub with docstring
   - Docstring: "Phase 1: no-op (read-only). Phase 4: merge-insert into ~/.pi/agent/auth.json with atomic write, 0o600 permissions, preserve other providers' keys."
   - Purpose: Establishes the interface contract for Phase 4 without writing anything in Phase 1
3. Implement `get_api_key(provider: str)`
   - Map provider to env var name (`MINIMAX_CN_API_KEY` for `minimax-cn`, `KIMI_API_KEY` for `kimi-coding`)
   - Read from env var first, fallback to `auth.json`
   - This is read-only — does NOT write auth.json
4. Implement `get_default_provider()` → `"minimax-cn"` and `get_default_model()` → `"MiniMax-M2.7"`
5. Add logging (never log API key values)
6. Write unit tests

**Environment Variable Mapping**:

| Provider | Env Var | Notes |
|----------|---------|-------|
| `minimax-cn` | `MINIMAX_CN_API_KEY` | **Default for MVP** |
| `kimi-coding` | `KIMI_API_KEY` | Free backup |
| `anthropic` | `ANTHROPIC_API_KEY` | Future expansion |
| `openai` | `OPENAI_API_KEY` | Future expansion |

**Deliverables**:
- `openrecall/client/chat/config_manager.py`
- `tests/test_chat_config_manager.py`

**Validation**:
```bash
export MINIMAX_CN_API_KEY=sk-test
python -c "from openrecall.client.chat.config_manager import get_api_key; print(get_api_key('minimax-cn'))"
# Output: sk-test

# Also verify auth.json fallback:
python -c "from openrecall.client.chat.config_manager import get_api_key; print(get_api_key('minimax-cn'))"
# Reads from ~/.pi/agent/auth.json if env var not set
```

---

### Task 1.3: Model Definitions

**File**: `openrecall/client/chat/models.py`

**Estimated effort**: Small

**Rationale**: Pi is the authoritative source for all built-in model metadata (context windows, cost, capabilities). MyRecall only needs default provider/model constants — no model metadata dictionary is maintained.

**Steps**:

1. Create `openrecall/client/chat/models.py` with:

   ```python
   DEFAULT_PROVIDER = "minimax-cn"
   DEFAULT_MODEL = "MiniMax-M2.7"
   ```

2. Add a docstring explaining:
   - Pi maintains all built-in model metadata internally
   - `DEFAULT_PROVIDER` and `DEFAULT_MODEL` are the only values MyRecall needs
   - No `MYRECALL_MODELS` dictionary is defined here

**Deliverables**:
- `openrecall/client/chat/models.py`

**Validation**:
```bash
python -c "from openrecall.client.chat.models import DEFAULT_PROVIDER, DEFAULT_MODEL; print(DEFAULT_PROVIDER, DEFAULT_MODEL)"
# Output: minimax-cn MiniMax-M2.7
```

---

### Task 1.4: myrecall-search Skill

**File**: `openrecall/client/chat/skills/myrecall-search/SKILL.md`

**Estimated effort**: Medium

**Status**: ✅ **Completed** — skill file already exists at `openrecall/client/chat/skills/myrecall-search/SKILL.md`

**Steps** (already completed):

1. ✅ Created skill directory structure: `openrecall/client/chat/skills/myrecall-search/`
2. ✅ Written SKILL.md with:
   - YAML frontmatter (`name: myrecall-search`, `description`)
   - Context window protection rules
   - API endpoint documentation for all 4 MVP endpoints
   - Agent policy (progressive disclosure, default tool strategy)
   - Examples and best practices
3. ✅ Referenced screenpipe's `screenpipe-api/SKILL.md` for structure
4. ✅ `pi_manager.ensure_skill_installed()` copies skill to `~/.pi/agent/skills/`

**Deliverables**:
- `openrecall/client/chat/skills/myrecall-search/SKILL.md` ✅

---

### Task 1.5: Integration Test

**File**: `tests/test_chat_pi_integration.py`

**Estimated effort**: Medium

**Steps**:

1. Create test fixtures and mocks
2. Test Pi installation
   - Verify installation succeeds
   - Verify version check works
3. Test config management
   - Verify API key resolution from env var (MINIMAX_CN_API_KEY)
   - Verify API key resolution from auth.json fallback
   - **Phase 1: No auth.json write test** — ConfigManager is read-only
   - **A3: No models.json test** — Pi provides built-in minimax-cn + kimi-coding
4. Test Pi execution (basic)
   - **Pre-check**: Verify Edge server is reachable at `http://localhost:8083/v1/health`
   - **Pre-check**: Verify `MINIMAX_CN_API_KEY` or `KIMI_API_KEY` is set (skip Pi execution test if neither is available)
   - Run Pi with simple prompt targeting minimax-cn provider
   - Verify Pi can access `/v1/activity-summary`
   - Clean up after test

**Deliverables**:
- `tests/test_chat_pi_integration.py`
- Test marked as `@pytest.mark.integration`

**Validation**:
```bash
# Start Edge server first
./run_server.sh --debug

# Run integration test
pytest tests/test_chat_pi_integration.py -v
```

---

## Implementation Order

```
Task 1.1 (Pi Manager) ──┐
Task 1.2 (Config Manager) ├──► Task 1.5 (Integration Test)
Task 1.3 (Model Defs) ───┘
     │
     └──► Task 1.4 (Skill)
              │
              └──► Task 1.5 (Integration Test)
```

**Note**: Task 1.1, 1.2, and 1.3 are fully independent and can be developed in parallel.

## Timeline

| Task | Dependencies | Parallel? | Status |
|------|--------------|-----------|--------|
| 1.3 Models | None | Yes | ✅ Complete |
| 1.1 Pi Manager | None | Yes | ✅ Complete |
| 1.2 Config Manager | None | Yes | ✅ Complete |
| 1.4 Skill | None | Yes | ✅ Complete |
| 1.5 Integration | 1.1, 1.2, 1.4 | No | ✅ Complete |

**Completed: 2026-03-26** — All Phase 1 tasks finished and verified.

**Execution summary**:
1. Parallel: 1.1 + 1.2 + 1.3 completed
2. Sequential: 1.5 completed after dependencies
3. Task 1.4 was already done

## File Checklist

```
openrecall/client/chat/
├── __init__.py              [✅] Created
├── pi_manager.py            [✅] Implemented
├── config_manager.py        [✅] Implemented
├── models.py                [✅] Implemented
└── skills/
    └── myrecall-search/
        └── SKILL.md         [✅] Complete

tests/
├── test_chat_pi_manager.py      [✅] Written
├── test_chat_config_manager.py  [✅] Written
└── test_chat_pi_integration.py  [✅] Written
```

## Definition of Done

- [x] All files created and implemented
- [x] Unit tests pass: `pytest tests/test_chat_*.py -v`
- [x] Integration test passes (requires running Edge server)
- [x] Pi can be installed via `ensure_installed()`
- [x] `MINIMAX_CN_API_KEY` resolution works via `get_api_key('minimax-cn')`
- [x] `KIMI_API_KEY` resolution works via `get_api_key('kimi-coding')`
- [x] `get_api_key()` falls back to auth.json when env var not set
- [x] `validate_pi_config()` is a no-op stub (does not write auth.json in Phase 1)
- [x] `validate_pi_config()` interface documents Phase 4 merge-preserve semantics
- [x] `models.py` defines only `DEFAULT_PROVIDER` and `DEFAULT_MODEL` constants (no `MYRECALL_MODELS` dict)
- [x] Skill file valid and complete
- [x] Skill copied to `~/.pi/agent/skills/myrecall-search/SKILL.md` by `ensure_skill_installed()`
- [x] `content_type` deprecation: SKILL.md correctly documents it as deprecated and ignored
- [x] `mvp.md` updated: `recent_texts` includes `role` field, `descriptions` field documented

## Open Questions

| Question | Status | Resolution |
|----------|--------|------------|
| LLM Provider selection | **Resolved** | Use Pi's built-in `minimax-cn` as default provider. Provider: `minimax-cn`. Model: `MiniMax-M2.7`. API: `https://api.minimaxi.com/anthropic`, `anthropic-messages`. Auth: `MINIMAX_CN_API_KEY`. Keep `kimi-coding` (`KIMI_API_KEY`) as free backup. No custom `models.json` needed. |
| Phase 1 write auth.json? | **Resolved** | No — Phase 1 is read-only. `validate_pi_config()` is no-op. Users configure via `MINIMAX_CN_API_KEY` / `KIMI_API_KEY` env vars. Write auth.json deferred to Phase 4 (config UI). |
| bun bundling | Deferred | MVP requires user to install bun separately |
| Windows support | Deferred | Test on macOS first, Windows in Phase 2+ |

## Notes

### Provider Architecture (A3)

Two Pi built-in providers available:

**minimax-cn (default, China)**:
- **Endpoint**: `https://api.minimaxi.com/anthropic`
- **API**: `anthropic-messages`
- **Auth**: `MINIMAX_CN_API_KEY` env var
- **Models**: MiniMax-M2, M2.1, M2.5, M2.7 (each ±highspeed variant)
- **Context**: 204,800 tokens, max output 131,072

**kimi-coding (backup, free)**:
- **Endpoint**: `https://api.kimi.com/coding`
- **API**: `anthropic-messages`
- **Auth**: `KIMI_API_KEY` env var
- **Models**: `k2p5` (multimodal), `kimi-k2-thinking` (text-only)
- **Context**: 262,144 tokens
- **Cost**: Free (Moonshot sponsored)

No custom `models.json` entry needed — Pi auto-detects both providers.

### package.json Overrides

From screenpipe's `seed_pi_package_json`:
```json
{
  "overrides": {
    "hosted-git-info": {
      "lru-cache": "^10.0.0"
    }
  }
}
```
This fixes an ESM/CJS compatibility issue on Windows.

### Future: Writing auth.json (Phase 4+)

When Phase 4 adds a configuration UI, we will need to write auth.json. The pattern will be:

```python
# Merge-only write: preserve other providers' keys
tmp_path = config_dir.join(f"auth.json.{pid}.{thread_id}.tmp")
write(tmp_path, content)
rename(tmp_path, auth_path)  # Atomic on POSIX
os.chmod(auth_path, 0o600)   # User read/write only
```

Security rules for writing:
- Never log API keys
- Set auth.json permissions to 0o600 on Unix
- Always merge (never overwrite) to preserve other providers

### Screenpipe Comparison

Screenpipe (Tauri GUI) writes to auth.json AND sets env vars on the Pi subprocess:

```rust
// Write to auth.json for persistence
obj.insert("screenpipe".to_string(), json!(token));

// Set env var on subprocess for current run
cmd.env("SCREENPIPE_API_KEY", token);
```

Phase 1 defers this complexity. Users self-configure via env vars or manual auth.json editing.

## References

- **Pi minimax-cn Provider (China)**: `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4620)
- **Pi minimax Provider (international)**: `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4500)
- **Pi kimi-coding Provider**: `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4464)
- **Pi Providers Docs**: `_ref/pi-mono/packages/coding-agent/docs/providers.md`
- **Pi Models Docs**: `_ref/pi-mono/packages/coding-agent/docs/models.md`
- **Pi README**: `_ref/pi-mono/packages/coding-agent/README.md`
- **Pi Skills Docs**: `_ref/pi-mono/packages/coding-agent/docs/skills.md`
- **MyRecall MVP Spec**: `docs/v3/chat/mvp.md`
- **MyRecall Overview**: `docs/v3/chat/overview.md`
- **Phase1 Spec**: `docs/v3/chat/phase1-foundation/spec.md`
