# Test/Deploy Mode Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--mode local` / `--mode remote` flags to `run_client.sh` and `run_server.sh` that load corresponding TOML config files.

**Architecture:** Shell scripts parse `--mode` argument and resolve to `{name}-{mode}.toml` config file. Python entry point receives `--config` with the resolved path. No Python code changes needed.

**Tech Stack:** Bash shell scripts, TOML config files

---

## Task 1: Create `client-local.toml`

**Files:**
- Create: `client-local.toml`
- Reference: `client.toml`

- [ ] **Step 1: Create `client-local.toml`**

Base it on `client.toml` but set API URLs for local mode:

```toml
# OpenRecall Client Configuration — Local Mode
# Client + Edge on same machine (localhost)

# ==============================================================================
# Client Settings
# ==============================================================================
[client]
debug = true

# ==============================================================================
# Server Connection Settings
# ==============================================================================
[server]
api_url = "http://localhost:8083/api"   # Local Edge server
edge_base_url = "http://localhost:8083"  # Local Edge base URL
upload_timeout = 180

# ==============================================================================
# Path Settings
# ==============================================================================
[paths]
data_dir = "~/.myrecall/client"
buffer_dir = "~/.myrecall/buffer"

# ==============================================================================
# Capture Settings
# ==============================================================================
[capture]
primary_monitor_only = true
save_local_copies = false
permission_poll_sec = 10

# ==============================================================================
# Debounce Settings (in milliseconds)
# ==============================================================================
[debounce]
click_ms = 3000
trigger_ms = 3000
capture_ms = 3000
idle_interval_ms = 60000

# ==============================================================================
# Deduplication Settings
# ==============================================================================
[dedup]
enabled = true
threshold = 10
ttl_seconds = 60.0
cache_size_per_device = 1
for_click = true
for_app_switch = false
force_after_skip_seconds = 30

# ==============================================================================
# UI Settings
# ==============================================================================
[ui]
web_enabled = true
web_port = 8889

# ==============================================================================
# Stats Settings
# ==============================================================================
[stats]
interval_sec = 120
```

- [ ] **Step 2: Commit**

```bash
git add client-local.toml
git commit -m "feat: add client-local.toml for local testing mode"
```

---

## Task 2: Create `client-remote.toml`

**Files:**
- Create: `client-remote.toml`
- Reference: `client.toml`

- [ ] **Step 1: Create `client-remote.toml`**

Base it on `client.toml` but set API URLs for remote/deployed mode:

```toml
# OpenRecall Client Configuration — Remote/Deployed Mode
# Client on local machine, Edge on remote server (10.77.3.162)

# ==============================================================================
# Client Settings
# ==============================================================================
[client]
debug = true

# ==============================================================================
# Server Connection Settings
# ==============================================================================
[server]
api_url = "http://10.77.3.162:8083/api"   # Remote Edge server
edge_base_url = "http://10.77.3.162:8083"  # Remote Edge base URL
upload_timeout = 180

# ==============================================================================
# Path Settings
# ==============================================================================
[paths]
data_dir = "~/.myrecall/client"
buffer_dir = "~/.myrecall/buffer"

# ==============================================================================
# Capture Settings
# ==============================================================================
[capture]
primary_monitor_only = true
save_local_copies = false
permission_poll_sec = 10

# ==============================================================================
# Debounce Settings (in milliseconds)
# ==============================================================================
[debounce]
click_ms = 3000
trigger_ms = 3000
capture_ms = 3000
idle_interval_ms = 60000

# ==============================================================================
# Deduplication Settings
# ==============================================================================
[dedup]
enabled = true
threshold = 10
ttl_seconds = 60.0
cache_size_per_device = 1
for_click = true
for_app_switch = false
force_after_skip_seconds = 30

# ==============================================================================
# UI Settings
# ==============================================================================
[ui]
web_enabled = true
web_port = 8889

# ==============================================================================
# Stats Settings
# ==============================================================================
[stats]
interval_sec = 120
```

- [ ] **Step 2: Commit**

```bash
git add client-remote.toml
git commit -m "feat: add client-remote.toml for deployed mode"
```

---

## Task 3: Create `server-local.toml`

**Files:**
- Create: `server-local.toml`
- Reference: `server.toml`

- [ ] **Step 1: Create `server-local.toml`**

Base it on `server.toml` but set server host for local mode:

```toml
# OpenRecall Server Configuration — Local Mode
# Server listens on localhost only (127.0.0.1)

# ==============================================================================
# Server Settings
# ==============================================================================
[server]
host = "127.0.0.1"   # Localhost only — not accessible from other machines
port = 8083
debug = true

# ==============================================================================
# Path Settings
# ==============================================================================
[paths]
data_dir = "~/.myrecall/server"
cache_dir = "~/.myrecall/cache"

# ==============================================================================
# AI Provider (Global fallback for vision, embedding, description)
# ==============================================================================
[ai]
provider = "openai"
device = "cpu"
model_name = ""
api_key = ""
api_base = ""
request_timeout = 120

# ==============================================================================
# OCR Settings
# ==============================================================================
[ocr]
provider = "rapidocr"
model_name = ""
rapid_version = "PP-OCRv4"
model_type = "mobile"

# ==============================================================================
# Description Generation (Frame AI Analysis)
# ==============================================================================
[description]
enabled = true
provider = "openai"
model = "Qwen/Qwen3-VL-8B-Instruct"
api_key = ""
api_base = "http://127.0.0.1:8090/v1"

# ==============================================================================
# Reranker Settings
# ==============================================================================
[reranker]
enabled = false
mode = "api"
url = "http://localhost:8083/rerank"
model = "Qwen/Qwen3-Reranker-0.6B"
api_key = ""

# ==============================================================================
# Processing Settings
# ==============================================================================
[processing]
mode = "ocr"
queue_capacity = 500
preload_models = true

# ==============================================================================
# UI Settings
# ==============================================================================
[ui]
show_ai_description = true

# ==============================================================================
# Advanced Settings
# ==============================================================================
[advanced]
fusion_log_enabled = false
```

- [ ] **Step 2: Commit**

```bash
git add server-local.toml
git commit -m "feat: add server-local.toml for local testing mode"
```

---

## Task 4: Create `server-remote.toml`

**Files:**
- Create: `server-remote.toml`
- Reference: `server.toml`

- [ ] **Step 1: Create `server-remote.toml`**

Base it on `server.toml` but set server host for remote/deployed mode (bind to `0.0.0.0` so it's accessible from other machines):

```toml
# OpenRecall Server Configuration — Remote/Deployed Mode
# Server listens on all interfaces (0.0.0.0) — accessible from other machines

# ==============================================================================
# Server Settings
# ==============================================================================
[server]
host = "0.0.0.0"   # All interfaces — accessible from client machines
port = 8083
debug = true

# ==============================================================================
# Path Settings
# ==============================================================================
[paths]
data_dir = "~/.myrecall/server"
cache_dir = "~/.myrecall/cache"

# ==============================================================================
# AI Provider (Global fallback for vision, embedding, description)
# ==============================================================================
[ai]
provider = "openai"
device = "cpu"
model_name = ""
api_key = ""
api_base = ""
request_timeout = 120

# ==============================================================================
# OCR Settings
# ==============================================================================
[ocr]
provider = "rapidocr"
model_name = ""
rapid_version = "PP-OCRv4"
model_type = "mobile"

# ==============================================================================
# Description Generation (Frame AI Analysis)
# ==============================================================================
[description]
enabled = true
provider = "openai"
model = "Qwen/Qwen3-VL-8B-Instruct"
api_key = ""
api_base = "http://127.0.0.1:8090/v1"

# ==============================================================================
# Reranker Settings
# ==============================================================================
[reranker]
enabled = false
mode = "api"
url = "http://localhost:8083/rerank"
model = "Qwen/Qwen3-Reranker-0.6B"
api_key = ""

# ==============================================================================
# Processing Settings
# ==============================================================================
[processing]
mode = "ocr"
queue_capacity = 500
preload_models = true

# ==============================================================================
# UI Settings
# ==============================================================================
[ui]
show_ai_description = true

# ==============================================================================
# Advanced Settings
# ==============================================================================
[advanced]
fusion_log_enabled = false
```

- [ ] **Step 2: Commit**

```bash
git add server-remote.toml
git commit -m "feat: add server-remote.toml for deployed mode"
```

---

## Task 5: Add `--mode` to `run_client.sh`

**Files:**
- Modify: `run_client.sh`

- [ ] **Step 1: Add `--mode` argument parsing**

Read `run_client.sh` first, then edit it. Add `--mode` parsing after the existing argument parsing block (after the `done` for the `for arg in "$@"` loop, before the config source priority block).

Find this line in `run_client.sh`:
```bash
# Config source priority: --config (TOML) > --env (legacy) > default paths
```

And add `--mode` handling **before** it:

```bash
# Mode-based config selection (overrides auto-discovery but not --config)
if [[ -n "$mode" ]]; then
  case "$mode" in
    local)
      config_file="$repo_root/client-local.toml"
      ;;
    remote)
      config_file="$repo_root/client-remote.toml"
      ;;
    *)
      echo "Error: unknown --mode value '$mode'. Use 'local' or 'remote'." >&2
      echo "Usage: $0 [--debug] [--mode local|remote] [--config=/abs/path] [--env=/abs/path]" >&2
      exit 2
      ;;
  esac
  echo "[Mode] Loading config: $config_file"
fi
```

Then find this block in `run_client.sh`:
```bash
for arg in "$@"; do
  case "$arg" in
    --debug)
      enable_debug="true"
      ;;
    --no-web)
```

And add `--mode` parsing inside the case statement (add after `--no-web`):
```bash
    --mode=*)
      mode="${arg#--mode=}"
      ;;
    --mode)
      shift
      mode="${1:-}"
      ;;
```

Also add `mode=""` to the variable declarations at the top (find `config_file=""` and `env_file=""` and add `mode=""` nearby).

- [ ] **Step 2: Verify the modification**

Read the modified `run_client.sh` and check:
1. `mode=""` is declared near other variables
2. `--mode=*` and `--mode` cases are in the argument parser
3. `--mode` block (with case statement for local/remote) appears before the config priority block
4. `config_file` is set by `--mode` block before the priority check runs

The flow should be:
```
parse args → --mode sets config_file → config priority runs → exec python
```

- [ ] **Step 3: Commit**

```bash
git add run_client.sh
git commit -m "feat(run_client): add --mode local/remote flag for config switching"
```

---

## Task 6: Add `--mode` to `run_server.sh`

**Files:**
- Modify: `run_server.sh`

- [ ] **Step 1: Add `--mode` argument parsing**

Read `run_server.sh` first, then edit it. This is the same pattern as Task 5 but for `server-local.toml` and `server-remote.toml`.

Add `mode=""` to variable declarations (find `config_file=""` and add `mode=""` nearby).

Add `--mode=*` and `--mode` case entries in the argument parser:

```bash
    --mode=*)
      mode="${arg#--mode=}"
      ;;
    --mode)
      shift
      mode="${1:-}"
      ;;
```

Add the mode selection block **before** the config source priority block (before `# Config source priority...`):

```bash
# Mode-based config selection (overrides auto-discovery but not --config)
if [[ -n "$mode" ]]; then
  case "$mode" in
    local)
      config_file="$repo_root/server-local.toml"
      ;;
    remote)
      config_file="$repo_root/server-remote.toml"
      ;;
    *)
      echo "Error: unknown --mode value '$mode'. Use 'local' or 'remote'." >&2
      echo "Usage: $0 [--debug] [--mode local|remote] [--config=/abs/path] [--env=/abs/path]" >&2
      exit 2
      ;;
  esac
  echo "[Mode] Loading config: $config_file"
fi
```

- [ ] **Step 2: Verify the modification**

Same verification steps as Task 5 Step 2 but for `run_server.sh`.

- [ ] **Step 3: Commit**

```bash
git add run_server.sh
git commit -m "feat(run_server): add --mode local/remote flag for config switching"
```

---

## Task 7: Write shell script tests

**Files:**
- Create: `tests/test_run_scripts_mode.py`

- [ ] **Step 1: Write tests for `--mode` flag parsing**

This is a Python test file that uses `subprocess` to verify the shell scripts parse `--mode` correctly. Since we can't easily mock the Python execution, we verify by checking the usage message and the config resolution logic.

```python
"""Tests for run_client.sh and run_server.sh --mode flag."""
import subprocess
import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent


def test_client_mode_local_unknown_shows_error():
    """Unknown --mode value should exit with code 2 and show usage."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_client.sh"), "--mode", "invalid"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unknown --mode value" in result.stderr
    assert "local" in result.stderr
    assert "remote" in result.stderr


def test_client_mode_remote_unknown_shows_error():
    """Unknown --mode value should exit with code 2 for remote too."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_client.sh"), "--mode=invalid"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unknown --mode value" in result.stderr


def test_client_mode_local_missing_config_exits():
    """--mode local with missing config should exit with code 1."""
    # Temporarily rename client-local.toml so the script can't find it
    config_path = REPO_ROOT / "client-local.toml"
    backup_path = REPO_ROOT / "client-local.toml.bak"

    if config_path.exists():
        config_path.rename(backup_path)
    try:
        result = subprocess.run(
            ["bash", str(REPO_ROOT / "run_client.sh"), "--mode", "local"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Config file not found" in result.stderr or "client-local.toml" in result.stderr
    finally:
        if backup_path.exists():
            backup_path.rename(config_path)


def test_server_mode_local_unknown_shows_error():
    """Unknown --mode value should exit with code 2."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_server.sh"), "--mode", "unknown"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unknown --mode value" in result.stderr


def test_server_mode_remote_unknown_shows_error():
    """Unknown --mode value should exit with code 2."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_server.sh"), "--mode=unknown"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_client_mode_local_config_exists():
    """--mode local should resolve to client-local.toml."""
    config_path = REPO_ROOT / "client-local.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_client_mode_remote_config_exists():
    """--mode remote should resolve to client-remote.toml."""
    config_path = REPO_ROOT / "client-remote.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_server_mode_local_config_exists():
    """--mode local should resolve to server-local.toml."""
    config_path = REPO_ROOT / "server-local.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_server_mode_remote_config_exists():
    """--mode remote should resolve to server-remote.toml."""
    config_path = REPO_ROOT / "server-remote.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_client_mode_local_e2e():
    """--mode local should produce correct config path in output."""
    # Check the script echoes the config path
    result = subprocess.run(
        ["bash", "-c",
         f"cd {REPO_ROOT} && bash run_client.sh --mode local --help 2>&1 || true"],
        capture_output=True,
        text=True,
    )
    # Should show the local config path in output (even if --help fails, the echo should appear)
    combined = result.stdout + result.stderr
    # The --help won't work (client doesn't have --help), but the mode echo should still appear
    # We check that client-local.toml was attempted
    assert "client-local.toml" in combined or result.returncode != 0


def test_client_no_mode_no_error():
    """No --mode flag should not produce errors (backward compat)."""
    # With no args and no config file, it should try defaults and fail gracefully
    # (either no config found or can't find python)
    result = subprocess.run(
        ["bash", "-c",
         f"cd {REPO_ROOT} && bash run_client.sh 2>&1 || true"],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    # Should NOT contain "unknown --mode" or parsing errors
    assert "unknown --mode" not in combined
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_run_scripts_mode.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_run_scripts_mode.py
git commit -m "test: add --mode flag parsing tests for run_client.sh and run_server.sh"
```

---

## Task 8 (Optional): Rename existing TOMLs to `.example`

**Files:**
- Rename: `client.toml` → `client.toml.example`
- Rename: `server.toml` → `server.toml.example`

This prevents accidental auto-loading of the current configs. It also makes the new mode-specific files the canonical configs.

- [ ] **Step 1: Rename `client.toml`**

```bash
mv client.toml client.toml.example
```

- [ ] **Step 2: Rename `server.toml`**

```bash
mv server.toml server.toml.example
```

- [ ] **Step 3: Commit**

```bash
git add client.toml.example server.toml.example
git rm client.toml server.toml
git commit -m "chore: rename client.toml and server.toml to .example templates"
```

---

## Self-Review Checklist

After all tasks:

1. **Spec coverage**: Every spec requirement is implemented:
   - [x] `--mode local` / `--mode remote` flags for client
   - [x] `--mode local` / `--mode remote` flags for server
   - [x] Config files created (client-local.toml, client-remote.toml, server-local.toml, server-remote.toml)
   - [x] Backward compat: `--config` still works
   - [x] Error handling: unknown mode exits with code 2
   - [x] Error handling: missing config exits with code 1
   - [x] Tests for shell script parsing

2. **Placeholder scan**: No TBD, TODO, or vague steps. All code is complete.

3. **Type consistency**: N/A (no Python code changes, only shell + TOML)

4. **Git hygiene**: Each task commits separately with descriptive messages.
