# MyRecall-v3 TOML Configuration Design

**Date**: 2026-03-31
**Status**: Approved
**Replaces**: `myrecall_server.env`, `myrecall_client.env`

---

## Overview

Replace the existing `.env` file-based configuration with TOML files, enabling distributed deployment where server and client run on separate machines with independent configurations.

**Key Goals**:
- Clean separation: `server.toml` (server machine) vs `client.toml` (client machine)
- Human-readable format with logical grouping
- Minimal changes: same parameter names, grouped into sections
- No hardware tier detection, no API keys, no migration from `.env`

---

## Architecture

### File Structure

```
~/.myrecall/
├── server.toml      # Server machine
└── client.toml      # Client machine
```

**Alternative locations** (checked in order):
1. `./server.toml` or `./client.toml` (project directory)
2. `~/.myrecall/server.toml` or `~/.myrecall/client.toml` (user home)

### Loading Precedence

```
Command-line override > Environment variable > Default TOML path
```

- CLI flag: `--config=/path/to.toml`
- Env var: `OPENRECALL_CONFIG_PATH=/path/to.toml`

---

## `server.toml` Schema

**File**: `~/.myrecall/server.toml`
**Used by**: `python -m openrecall.server`

```toml
# MyRecall Server Configuration

[server]
host = "0.0.0.0"
port = 8083
debug = false

[paths]
data_dir = "~/.myrecall/server"
cache_dir = "~/.myrecall/cache"

[ai]
provider = "local"
device = "cpu"
model_name = ""
api_key = ""
api_base = ""

[vision]
provider = ""
model_name = ""
api_key = ""
api_base = ""

[ocr]
provider = "rapidocr"
model_name = ""
rapid_version = "PP-OCRv4"
model_type = "mobile"
det_db_thresh = 0.3
det_db_box_thresh = 0.7
det_db_unclip_ratio = 1.6
det_limit_side_len = 960

[embedding]
provider = ""
model_name = "qwen-text-v1"
dim = 1024
api_key = ""
api_base = ""

[description]
enabled = true
provider = "local"     # Independent provider, no fallback to [ai]
model = ""
api_key = ""
api_base = ""
# NOTE: [description] is completely INDEPENDENT from [ai] section.
# Must be configured explicitly - no fallback to [ai] settings.

[reranker]
enabled = false
mode = "api"
url = "http://localhost:8080/rerank"
model = "Qwen/Qwen3-Reranker-0.6B"
api_key = ""

[processing]
mode = "ocr"
queue_capacity = 200
lifo_threshold = 10
preload_models = true

[ui]
show_ai_description = true

[advanced]
fusion_log_enabled = false
```

---

## `client.toml` Schema

**File**: `~/.myrecall/client.toml`
**Used by**: `python -m openrecall.client`

```toml
# MyRecall Client Configuration

[client]
debug = false

[server]
api_url = "http://localhost:8083/api"
edge_base_url = "http://localhost:8083"
upload_timeout = 180

[paths]
data_dir = "~/.myrecall/client"
buffer_dir = "~/.myrecall/buffer"

[capture]
primary_monitor_only = true
save_local_copies = false
permission_poll_sec = 10

[debounce]
click_ms = 3000
trigger_ms = 3000
capture_ms = 3000
idle_interval_ms = 60000

[dedup]
enabled = true
threshold = 10
ttl_seconds = 60.0
cache_size_per_device = 1
for_click = true
for_app_switch = false
force_after_skip_seconds = 30

[ui]
web_enabled = true
web_port = 8889

[stats]
interval_sec = 120
```

---

## Parameter Mapping

### Server Parameters

| .env Variable | TOML Path | Type | Default |
|---------------|-----------|------|---------|
| `OPENRECALL_HOST` | `[server] host` | str | `"0.0.0.0"` |
| `OPENRECALL_PORT` | `[server] port` | int | `8083` |
| `OPENRECALL_DEBUG` | `[server] debug` | bool | `false` |
| `OPENRECALL_SERVER_DATA_DIR` | `[paths] data_dir` | Path | `~/.myrecall/server` |
| `OPENRECALL_CACHE_DIR` | `[paths] cache_dir` | Path | `~/.myrecall/cache` |
| `OPENRECALL_AI_PROVIDER` | `[ai] provider` | str | `"local"` |
| `OPENRECALL_DEVICE` | `[ai] device` | str | `"cpu"` |
| `OPENRECALL_AI_MODEL_NAME` | `[ai] model_name` | str | `""` |
| `OPENRECALL_AI_API_KEY` | `[ai] api_key` | str | `""` |
| `OPENRECALL_AI_API_BASE` | `[ai] api_base` | str | `""` |
| `OPENRECALL_VISION_PROVIDER` | `[vision] provider` | str | `""` |
| `OPENRECALL_OCR_PROVIDER` | `[ocr] provider` | str | `"rapidocr"` |
| `OPENRECALL_OCR_RAPID_OCR_VERSION` | `[ocr] rapid_version` | str | `"PP-OCRv4"` |
| `OPENRECALL_OCR_RAPID_MODEL_TYPE` | `[ocr] model_type` | str | `"mobile"` |
| `OPENRECALL_OCR_DET_DB_THRESH` | `[ocr] det_db_thresh` | float | `0.3` |
| `OPENRECALL_OCR_DET_DB_BOX_THRESH` | `[ocr] det_db_box_thresh` | float | `0.7` |
| `OPENRECALL_OCR_DET_DB_UNCLIP_RATIO` | `[ocr] det_db_unclip_ratio` | float | `1.6` |
| `OPENRECALL_OCR_DET_LIMIT_SIDE_LEN` | `[ocr] det_limit_side_len` | int | `960` |
| `OPENRECALL_EMBEDDING_MODEL_NAME` | `[embedding] model_name` | str | `"qwen-text-v1"` |
| `OPENRECALL_EMBEDDING_DIM` | `[embedding] dim` | int | `1024` |
| `OPENRECALL_DESCRIPTION_ENABLED` | `[description] enabled` | bool | `true` |
| `OPENRECALL_RERANKER_MODE` | `[reranker] mode` | str | `"api"` |
| `OPENRECALL_RERANKER_URL` | `[reranker] url` | str | `""` |
| `OPENRECALL_RERANKER_MODEL` | `[reranker] model` | str | `""` |
| `OPENRECALL_PROCESSING_MODE` | `[processing] mode` | str | `"ocr"` |
| `OPENRECALL_QUEUE_CAPACITY` | `[processing] queue_capacity` | int | `200` |
| `OPENRECALL_PROCESSING_LIFO_THRESHOLD` | `[processing] lifo_threshold` | int | `10` |
| `OPENRECALL_PRELOAD_MODELS` | `[processing] preload_models` | bool | `true` |
| `OPENRECALL_SHOW_AI_DESCRIPTION` | `[ui] show_ai_description` | bool | `true` |

### Client Parameters

| .env Variable | TOML Path | Type | Default |
|---------------|-----------|------|---------|
| `OPENRECALL_DEBUG` | `[client] debug` | bool | `false` |
| `OPENRECALL_API_URL` | `[server] api_url` | str | `"http://localhost:8083/api"` |
| `OPENRECALL_EDGE_BASE_URL` | `[server] edge_base_url` | str | `"http://localhost:8083"` |
| `OPENRECALL_UPLOAD_TIMEOUT` | `[server] upload_timeout` | int | `180` |
| `OPENRECALL_CLIENT_DATA_DIR` | `[paths] data_dir` | Path | `~/.myrecall/client` |
| `OPENRECALL_PRIMARY_MONITOR_ONLY` | `[capture] primary_monitor_only` | bool | `true` |
| `OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS` | `[capture] save_local_copies` | bool | `false` |
| `OPENRECALL_PERMISSION_POLL_INTERVAL_SEC` | `[capture] permission_poll_sec` | int | `10` |
| `OPENRECALL_CLICK_DEBOUNCE_MS` | `[debounce] click_ms` | int | `3000` |
| `OPENRECALL_TRIGGER_DEBOUNCE_MS` | `[debounce] trigger_ms` | int | `3000` |
| `OPENRECALL_CAPTURE_DEBOUNCE_MS` | `[debounce] capture_ms` | int | `3000` |
| `OPENRECALL_IDLE_CAPTURE_INTERVAL_MS` | `[debounce] idle_interval_ms` | int | `60000` |
| `OPENRECALL_SIMHASH_DEDUP_ENABLED` | `[dedup] enabled` | bool | `true` |
| `OPENRECALL_SIMHASH_DEDUP_THRESHOLD` | `[dedup] threshold` | int | `10` |
| `OPENRECALL_SIMHASH_TTL_SECONDS` | `[dedup] ttl_seconds` | float | `60.0` |
| `OPENRECALL_SIMHASH_CACHE_SIZE_PER_DEVICE` | `[dedup] cache_size_per_device` | int | `1` |
| `OPENRECALL_SIMHASH_ENABLED_FOR_CLICK` | `[dedup] for_click` | bool | `true` |
| `OPENRECALL_SIMHASH_ENABLED_FOR_APP_SWITCH` | `[dedup] for_app_switch` | bool | `false` |
| `OPENRECALL_FORCE_CAPTURE_AFTER_SECONDS` | `[dedup] force_after_skip_seconds` | int | `30` |
| `OPENRECALL_CLIENT_WEB_ENABLED` | `[ui] web_enabled` | bool | `true` |
| `OPENRECALL_CLIENT_WEB_PORT` | `[ui] web_port` | int | `8889` |
| `OPENRECALL_STATS_INTERVAL_SEC` | `[stats] interval_sec` | int | `120` |

---

## Implementation

### File: `openrecall/shared/config_base.py` (new)

Base class for TOML configuration:

```python
import tomllib
from pathlib import Path
from typing import Any

class TOMLConfig:
    """Base class for TOML-based configuration."""
    
    @classmethod
    def from_toml(cls, path: str | Path | None = None) -> "Self":
        """Load config from TOML file with fallback to defaults."""
        config_path = cls._find_config_path(path)
        if config_path and config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            return cls._from_dict(data)
        return cls._from_dict({})
    
    @classmethod
    def _find_config_path(cls, path: str | Path | None) -> Path | None:
        """Search for config file in standard locations."""
        # 1. Explicit path
        if path:
            return Path(path)
        # 2. Environment variable
        if env_path := os.environ.get("OPENRECALL_CONFIG_PATH"):
            return Path(env_path)
        # 3. Project directory
        if (project_path := Path.cwd() / cls._default_filename()).exists():
            return project_path
        # 4. User home directory
        if (home_path := Path.home() / ".myrecall" / cls._default_filename()).exists():
            return home_path
        return None
    
    @classmethod
    def _default_filename(cls) -> str:
        raise NotImplementedError
    
    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Self":
        raise NotImplementedError
```

### File: `openrecall/server/config_server.py` (new)

```python
class ServerSettings(TOMLConfig):
    """Server configuration loaded from server.toml."""
    
    @classmethod
    def _default_filename(cls) -> str:
        return "server.toml"
    
    # server.*
    host: str = "0.0.0.0"
    port: int = 8083
    debug: bool = False
    
    # paths.*
    data_dir: Path = Path("~/.myrecall/server")
    cache_dir: Path = Path("~/.myrecall/cache")
    
    # ai.*
    ai_provider: str = "local"
    device: str = "cpu"
    # ...
```

### File: `openrecall/client/config_client.py` (new)

```python
class ClientSettings(TOMLConfig):
    """Client configuration loaded from client.toml."""
    
    @classmethod
    def _default_filename(cls) -> str:
        return "client.toml"
    
    # server.* (connection to server)
    api_url: str = "http://localhost:8083/api"
    edge_base_url: str = "http://localhost:8083"
    upload_timeout: int = 180
    
    # dedup.*
    simhash_dedup_enabled: bool = True
    # ...
```

---

## Backwards Compatibility (Optional)

During transition period, detect `.env` files and use them if TOML is missing:

```python
def _find_config_path(cls, path: str | Path | None) -> Path | None:
    # Check TOML first
    toml_path = super()._find_config_path(path)
    if toml_path:
        return toml_path
    
    # Fallback to .env for migration period
    env_path = Path.cwd() / cls._default_env_filename()
    if env_path.exists():
        logger.warning(f"Using deprecated .env file: {env_path}")
        return env_path
    return None
```

Default env filenames: `myrecall_server.env`, `myrecall_client.env`

---

## Removed / Deprecated Parameters

The following parameters are **removed** (not used in v3):

| Parameter | Reason |
|-----------|--------|
| `OPENRECALL_SIMILARITY_THRESHOLD` | Legacy MSSIM, replaced by simhash |
| `OPENRECALL_DISABLE_SIMILARITY_FILTER` | Redundant with `simhash_dedup_enabled` |
| `OPENRECALL_DATA_DIR` | Legacy alias for `server_data_dir` |

---

## Testing

1. Unit tests for `ServerSettings.from_toml()` and `ClientSettings.from_toml()`
2. Test missing config file → uses defaults
3. Test partial config file → fills missing with defaults
4. Test config precedence: CLI > env > default path

---

## Example Usage

**Server machine**:
```bash
# First run: auto-creates ~/.myrecall/server.toml with defaults
python -m openrecall.server

# Use custom config
python -m openrecall.server --config=/etc/myrecall/server.toml
```

**Client machine**:
```bash
# Configure server URL
# Edit ~/.myrecall/client.toml and set:
# [server]
# api_url = "http://192.168.1.100:8083/api"

python -m openrecall.client
```

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `openrecall/shared/config_base.py` | Create: TOMLConfig base class |
| `openrecall/server/config_server.py` | Create: ServerSettings |
| `openrecall/client/config_client.py` | Create: ClientSettings |
| `openrecall/shared/config.py` | Modify: Keep as fallback, mark deprecated |
| `openrecall/server/__main__.py` | Modify: Use ServerSettings |
| `openrecall/client/__main__.py` | Modify: Use ClientSettings |
| `run_server.sh` | Modify: Remove env file loading |
| `run_client.sh` | Modify: Remove env file loading |
| `myrecall_server.env.example` | Delete (replaced by server.toml) |
| `myrecall_client.env.example` | Delete (replaced by client.toml) |

---

## Rollout Plan

1. Create `config_base.py`, `config_server.py`, `config_client.py`
2. Modify `run_server.sh` / `run_client.sh` to pass `--config` flag
3. Keep old `config.py` as fallback during transition
4. Remove `.env` examples from repo (or mark as deprecated)
5. Update `AGENTS.md` to document new TOML approach
