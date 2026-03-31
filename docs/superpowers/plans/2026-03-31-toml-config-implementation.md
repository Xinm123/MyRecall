# TOML Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace .env-based configuration with TOML files for distributed MyRecall deployment (server.toml + client.toml).

**Architecture:** Two-phase approach: (1) Create new TOML config classes alongside existing config.py as fallback, (2) Update shell scripts to use new config system and deprecate .env files.

**Tech Stack:** Python 3.11+, tomllib (stdlib), pydantic, existing config.py patterns.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `openrecall/shared/config_base.py` | Create | TOMLConfig base class with file loading |
| `openrecall/server/config_server.py` | Create | ServerSettings with all server params |
| `openrecall/client/config_client.py` | Create | ClientSettings with all client params |
| `openrecall/shared/config.py` | Modify | Keep as fallback, add deprecation warning |
| `openrecall/server/__main__.py` | Modify | Use ServerSettings instead of Settings |
| `openrecall/client/__main__.py` | Modify | Use ClientSettings instead of Settings |
| `openrecall/server/main.py` | Create | Optional unified entry point |
| `openrecall/client/main.py` | Create | Optional unified entry point |
| `run_server.sh` | Modify | Remove env loading, pass --config |
| `run_client.sh` | Modify | Remove env loading, pass --config |
| `myrecall_server.env.example` | Delete | Replaced by server.toml |
| `myrecall_client.env.example` | Delete | Replaced by client.toml |

---

## Task 1: Create TOMLConfig Base Class

**Files:**
- Create: `openrecall/shared/config_base.py`
- Test: `tests/test_config_base.py`

- [ ] **Step 1: Write failing test for TOMLConfig loading**

```python
# tests/test_config_base.py
import pytest
from openrecall.shared.config_base import TOMLConfig

class ConcreteConfig(TOMLConfig):
    @classmethod
    def _default_filename(cls) -> str:
        return "test.toml"

    @classmethod
    def _from_dict(cls, data: dict) -> "ConcreteConfig":
        return cls(value=data.get("value", "default"))

    value: str = "default"

def test_load_from_missing_file_uses_defaults():
    """Missing config file should return defaults."""
    config = ConcreteConfig.from_toml("/nonexistent/path.toml")
    assert config.value == "default"

def test_load_from_existing_file():
    """Existing TOML file should override defaults."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
        f.write('value = "from_file"')
        path = f.name
    try:
        config = ConcreteConfig.from_toml(path)
        assert config.value == "from_file"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_base.py -v`
Expected: `ERROR - ModuleNotFoundError: No module named 'openrecall.shared.config_base'`

- [ ] **Step 3: Write minimal TOMLConfig base class**

```python
# openrecall/shared/config_base.py
"""Base class for TOML-based configuration."""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Self

logger = logging.getLogger(__name__)

class TOMLConfig:
    """Base class for TOML-based configuration with fallback to defaults."""

    @classmethod
    def from_toml(cls, path: str | Path | None = None) -> Self:
        """Load config from TOML file with fallback to defaults."""
        config_path = cls._find_config_path(path)
        if config_path and config_path.exists():
            try:
                import tomllib
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
                flat_data = cls._flatten_dict(data)
                return cls._from_dict(flat_data)
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}, using defaults")
                return cls._from_dict({})
        return cls._from_dict({})

    @classmethod
    def _find_config_path(cls, path: str | Path | None) -> Path | None:
        """Search for config file in standard locations."""
        if path:
            p = Path(path)
            if p.exists():
                return p
            return None

        # Environment variable
        if env_path := os.environ.get("OPENRECALL_CONFIG_PATH"):
            p = Path(env_path)
            if p.exists():
                return p
            return None

        # Project directory
        if (project_path := Path.cwd() / cls._default_filename()).exists():
            return project_path

        # User home directory
        if (home_path := Path.home() / ".myrecall" / cls._default_filename()).exists():
            return home_path

        return None

    @classmethod
    def _flatten_dict(cls, d: dict, parent_key: str = "", sep: str = ".") -> dict:
        """Flatten nested dict: {"server": {"port": 8083}} -> {"server.port": 8083}"""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(cls._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    @classmethod
    def _default_filename(cls) -> str:
        raise NotImplementedError

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_base.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add openrecall/shared/config_base.py tests/test_config_base.py
git commit -m "feat(config): add TOMLConfig base class for TOML-based settings"
```

---

## Task 2: Create ServerSettings

**Files:**
- Create: `openrecall/server/config_server.py`
- Test: `tests/test_config_server.py`

- [ ] **Step 1: Write failing test for ServerSettings**

```python
# tests/test_config_server.py
import pytest
from openrecall.server.config_server import ServerSettings

def test_server_settings_defaults():
    """ServerSettings should have correct defaults."""
    settings = ServerSettings._from_dict({})
    assert settings.server_host == "0.0.0.0"
    assert settings.server_port == 8083
    assert settings.ai_provider == "local"
    assert settings.ai_device == "cpu"

def test_server_settings_from_dict():
    """ServerSettings should parse flat dict correctly."""
    data = {
        "server.host": "127.0.0.1",
        "server.port": 9000,
        "ai.provider": "dashscope",
        "ai.device": "cuda",
    }
    settings = ServerSettings._from_dict(data)
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 9000
    assert settings.ai_provider == "dashscope"
    assert settings.ai_device == "cuda"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_server.py -v`
Expected: `ERROR - ModuleNotFoundError: No module named 'openrecall.server.config_server'`

- [ ] **Step 3: Write ServerSettings class**

```python
# openrecall/server/config_server.py
"""Server configuration loaded from server.toml."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Self

from openrecall.shared.config_base import TOMLConfig

logger = logging.getLogger(__name__)


class ServerSettings(TOMLConfig):
    """Server configuration loaded from server.toml."""

    # [server]
    server_host: str = "0.0.0.0"
    server_port: int = 8083
    server_debug: bool = False

    # [paths]
    paths_data_dir: Path = Path("~/.myrecall/server")
    paths_cache_dir: Path = Path("~/.myrecall/cache")

    # [ai]
    ai_provider: str = "local"
    ai_device: str = "cpu"
    ai_model_name: str = ""
    ai_api_key: str = ""
    ai_api_base: str = ""

    # [vision]
    vision_provider: str = ""
    vision_model_name: str = ""
    vision_api_key: str = ""
    vision_api_base: str = ""

    # [ocr]
    ocr_provider: str = "rapidocr"
    ocr_model_name: str = ""
    ocr_rapid_version: str = "PP-OCRv4"
    ocr_model_type: str = "mobile"
    ocr_det_db_thresh: float = 0.3
    ocr_det_db_box_thresh: float = 0.7
    ocr_det_db_unclip_ratio: float = 1.6
    ocr_det_limit_side_len: int = 960
    ocr_det_db_score_mode: int = 0  # Used in rapid_backend.py
    ocr_drop_score: float = 0.0  # Used in rapid_backend.py

    # [embedding]
    embedding_provider: str = ""
    embedding_model_name: str = "qwen-text-v1"
    embedding_dim: int = 1024
    embedding_api_key: str = ""
    embedding_api_base: str = ""

    # [description]
    description_enabled: bool = True
    description_provider: str = ""
    description_model: str = ""
    description_api_key: str = ""
    description_api_base: str = ""

    # [reranker]
    reranker_enabled: bool = False
    reranker_mode: str = "api"
    reranker_url: str = "http://localhost:8083/rerank"
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    reranker_api_key: str = ""

    # [processing]
    processing_mode: str = "ocr"
    processing_queue_capacity: int = 200
    processing_lifo_threshold: int = 10
    processing_preload_models: bool = True

    # [ui]
    ui_show_ai_description: bool = True

    # [advanced]
    advanced_fusion_log_enabled: bool = False

    @classmethod
    def _default_filename(cls) -> str:
        return "server.toml"

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """Create ServerSettings from flat dict (flattened TOML)."""
        # Use _Field access pattern for clean initialization
        return cls(
            server_host=data.get("server.host", "0.0.0.0"),
            server_port=data.get("server.port", 8083),
            server_debug=data.get("server.debug", False),
            paths_data_dir=Path(data.get("paths.data_dir", "~/.myrecall/server")),
            paths_cache_dir=Path(data.get("paths.cache_dir", "~/.myrecall/cache")),
            ai_provider=data.get("ai.provider", "local"),
            ai_device=data.get("ai.device", "cpu"),
            ai_model_name=data.get("ai.model_name", ""),
            ai_api_key=data.get("ai.api_key", ""),
            ai_api_base=data.get("ai.api_base", ""),
            vision_provider=data.get("vision.provider", ""),
            vision_model_name=data.get("vision.model_name", ""),
            vision_api_key=data.get("vision.api_key", ""),
            vision_api_base=data.get("vision.api_base", ""),
            ocr_provider=data.get("ocr.provider", "rapidocr"),
            ocr_model_name=data.get("ocr.model_name", ""),
            ocr_rapid_version=data.get("ocr.rapid_version", "PP-OCRv4"),
            ocr_model_type=data.get("ocr.model_type", "mobile"),
            ocr_det_db_thresh=data.get("ocr.det_db_thresh", 0.3),
            ocr_det_db_box_thresh=data.get("ocr.det_db_box_thresh", 0.7),
            ocr_det_db_unclip_ratio=data.get("ocr.det_db_unclip_ratio", 1.6),
            ocr_det_limit_side_len=data.get("ocr.det_limit_side_len", 960),
            ocr_det_db_score_mode=data.get("ocr.det_db_score_mode", 0),
            ocr_drop_score=data.get("ocr.drop_score", 0.0),
            embedding_provider=data.get("embedding.provider", ""),
            embedding_model_name=data.get("embedding.model_name", "qwen-text-v1"),
            embedding_dim=data.get("embedding.dim", 1024),
            embedding_api_key=data.get("embedding.api_key", ""),
            embedding_api_base=data.get("embedding.api_base", ""),
            description_enabled=data.get("description.enabled", True),
            description_provider=data.get("description.provider", ""),
            description_model=data.get("description.model", ""),
            description_api_key=data.get("description.api_key", ""),
            description_api_base=data.get("description.api_base", ""),
            reranker_enabled=data.get("reranker.enabled", False),
            reranker_mode=data.get("reranker.mode", "api"),
            reranker_url=data.get("reranker.url", "http://localhost:8083/rerank"),
            reranker_model=data.get("reranker.model", "Qwen/Qwen3-Reranker-0.6B"),
            reranker_api_key=data.get("reranker.api_key", ""),
            processing_mode=data.get("processing.mode", "ocr"),
            processing_queue_capacity=data.get("processing.queue_capacity", 200),
            processing_lifo_threshold=data.get("processing.lifo_threshold", 10),
            processing_preload_models=data.get("processing.preload_models", True),
            ui_show_ai_description=data.get("ui.show_ai_description", True),
            advanced_fusion_log_enabled=data.get("advanced.fusion_log_enabled", False),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_server.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/config_server.py tests/test_config_server.py
git commit -m "feat(config): add ServerSettings for server.toml"
```

---

## Task 3: Create ClientSettings

**Files:**
- Create: `openrecall/client/config_client.py`
- Test: `tests/test_config_client.py`

- [ ] **Step 1: Write failing test for ClientSettings**

```python
# tests/test_config_client.py
import pytest
from openrecall.client.config_client import ClientSettings

def test_client_settings_defaults():
    """ClientSettings should have correct defaults."""
    settings = ClientSettings._from_dict({})
    assert settings.server_api_url == "http://localhost:8083/api"
    assert settings.debounce_click_ms == 3000
    assert settings.dedup_enabled == True
    assert settings.dedup_threshold == 10

def test_client_settings_from_dict():
    """ClientSettings should parse flat dict correctly."""
    data = {
        "server.api_url": "http://192.168.1.100:8083/api",
        "debounce.click_ms": 5000,
        "dedup.enabled": False,
    }
    settings = ClientSettings._from_dict(data)
    assert settings.server_api_url == "http://192.168.1.100:8083/api"
    assert settings.debounce_click_ms == 5000
    assert settings.dedup_enabled == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_client.py -v`
Expected: `ERROR - ModuleNotFoundError: No module named 'openrecall.client.config_client'`

- [ ] **Step 3: Write ClientSettings class**

```python
# openrecall/client/config_client.py
"""Client configuration loaded from client.toml."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Self

from openrecall.shared.config_base import TOMLConfig

logger = logging.getLogger(__name__)


class ClientSettings(TOMLConfig):
    """Client configuration loaded from client.toml."""

    # [client]
    client_debug: bool = False

    # [server] - connection to server
    server_api_url: str = "http://localhost:8083/api"
    server_edge_base_url: str = "http://localhost:8083"
    server_upload_timeout: int = 180

    # [paths]
    paths_data_dir: Path = Path("~/.myrecall/client")
    paths_buffer_dir: Path = Path("~/.myrecall/buffer")

    # [capture]
    capture_primary_monitor_only: bool = True
    capture_save_local_copies: bool = False
    capture_permission_poll_sec: int = 10

    # [debounce]
    debounce_click_ms: int = 3000
    debounce_trigger_ms: int = 3000
    debounce_capture_ms: int = 3000
    debounce_idle_interval_ms: int = 60000

    # [dedup]
    dedup_enabled: bool = True
    dedup_threshold: int = 10
    dedup_ttl_seconds: float = 60.0
    dedup_cache_size_per_device: int = 1
    dedup_for_click: bool = True
    dedup_for_app_switch: bool = False
    dedup_force_after_skip_seconds: int = 30

    # [ui]
    ui_web_enabled: bool = True
    ui_web_port: int = 8889

    # [stats]
    stats_interval_sec: int = 120

    @classmethod
    def _default_filename(cls) -> str:
        return "client.toml"

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """Create ClientSettings from flat dict (flattened TOML)."""
        return cls(
            client_debug=data.get("client.debug", False),
            server_api_url=data.get("server.api_url", "http://localhost:8083/api"),
            server_edge_base_url=data.get("server.edge_base_url", "http://localhost:8083"),
            server_upload_timeout=data.get("server.upload_timeout", 180),
            paths_data_dir=Path(data.get("paths.data_dir", "~/.myrecall/client")),
            paths_buffer_dir=Path(data.get("paths.buffer_dir", "~/.myrecall/buffer")),
            capture_primary_monitor_only=data.get("capture.primary_monitor_only", True),
            capture_save_local_copies=data.get("capture.save_local_copies", False),
            capture_permission_poll_sec=data.get("capture.permission_poll_sec", 10),
            debounce_click_ms=data.get("debounce.click_ms", 3000),
            debounce_trigger_ms=data.get("debounce.trigger_ms", 3000),
            debounce_capture_ms=data.get("debounce.capture_ms", 3000),
            debounce_idle_interval_ms=data.get("debounce.idle_interval_ms", 60000),
            dedup_enabled=data.get("dedup.enabled", True),
            dedup_threshold=data.get("dedup.threshold", 10),
            dedup_ttl_seconds=data.get("dedup.ttl_seconds", 60.0),
            dedup_cache_size_per_device=data.get("dedup.cache_size_per_device", 1),
            dedup_for_click=data.get("dedup.for_click", True),
            dedup_for_app_switch=data.get("dedup.for_app_switch", False),
            dedup_force_after_skip_seconds=data.get("dedup.force_after_skip_seconds", 30),
            ui_web_enabled=data.get("ui.web_enabled", True),
            ui_web_port=data.get("ui.web_port", 8889),
            stats_interval_sec=data.get("stats.interval_sec", 120),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/config_client.py tests/test_config_client.py
git commit -m "feat(config): add ClientSettings for client.toml"
```

---

## Task 4: Create Example TOML Files

**Files:**
- Create: `myrecall_server.toml.example`
- Create: `myrecall_client.toml.example`

- [ ] **Step 1: Create server.toml.example**

```toml
# MyRecall Server Configuration
# Copy to ~/.myrecall/server.toml or ./server.toml

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
det_db_score_mode = 0  # Used by rapid_backend.py
drop_score = 0.0  # Used by rapid_backend.py

[embedding]
provider = ""
model_name = "qwen-text-v1"
dim = 1024
api_key = ""
api_base = ""

[description]
enabled = true
provider = ""
model = ""
api_key = ""
api_base = ""

[reranker]
enabled = false
mode = "api"
url = "http://localhost:8083/rerank"
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

- [ ] **Step 2: Create client.toml.example**

```toml
# MyRecall Client Configuration
# Copy to ~/.myrecall/client.toml or ./client.toml

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

- [ ] **Step 3: Commit**

```bash
git add myrecall_server.toml.example myrecall_client.toml.example
git commit -m "feat(config): add example TOML config files"
```

---

## Task 5: Update Shell Scripts

**Files:**
- Modify: `run_server.sh`
- Modify: `run_client.sh`

- [ ] **Step 1: Update run_server.sh**

Replace the env loading section (lines 8-40) with TOML config support:

```bash
# Determine config path (priority order)
CONFIG_PATH=""
for arg in "$@"; do
  case "$arg" in
    --config=*)
      CONFIG_PATH="${arg#--config=}"
      ;;
  esac
done

# If not passed as arg, check env var and standard locations
if [ -z "$CONFIG_PATH" ]; then
    CONFIG_PATH="${OPENRECALL_CONFIG_PATH:-}"
fi
if [ -z "$CONFIG_PATH" ]; then
    if [ -f "./server.toml" ]; then
        CONFIG_PATH="./server.toml"
    elif [ -f "$HOME/.myrecall/server.toml" ]; then
        CONFIG_PATH="$HOME/.myrecall/server.toml"
    fi
fi

# TOML config takes priority; env vars still loaded for backward compat
set -a
source "$env_file" 2>/dev/null || true
set +a

if [[ "$enable_debug" == "true" ]]; then
  export OPENRECALL_DEBUG=true
fi

exec "$python_bin" -m openrecall.server ${CONFIG_PATH:+--config="$CONFIG_PATH"} "$@"
```

Note: Keep existing `--env=` and `--debug` argument handling from original script.

- [ ] **Step 2: Update run_client.sh**

Apply same pattern for client.toml, preserving existing `--env=` and `--debug` handling.

- [ ] **Step 3: Commit**

```bash
git add run_server.sh run_client.sh
git commit -m "refactor(config): support TOML config in shell scripts"
```

---

## Task 6: Update __main__.py Entry Points

**Files:**
- Modify: `openrecall/server/__main__.py`
- Modify: `openrecall/client/__main__.py`

- [ ] **Step 1: Update server/__main__.py**

Add `--config` argument parsing:

```python
# openrecall/server/__main__.py additions
import argparse

def main():
    parser = argparse.ArgumentParser(description="MyRecall Server")
    parser.add_argument("--config", type=str, default=None, help="Path to server.toml config file")
    args, remaining = parser.parse_known_args()
    
    if args.config:
        settings = ServerSettings.from_toml(args.config)
    else:
        settings = ServerSettings.from_toml()
    
    # Rest of existing main() logic using settings...
```

- [ ] **Step 2: Update client/__main__.py similarly**

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/__main__.py openrecall/client/__main__.py
git commit -m "feat(config): add --config CLI argument to server and client entry points"
```

---

## Task 7: Deprecate Old config.py

**Files:**
- Modify: `openrecall/shared/config.py`

- [ ] **Step 1: Add deprecation warning to config.py Settings**

Add at the top of the file or in `__init__`:

```python
import warnings

warnings.warn(
    "openrecall.shared.config.Settings is deprecated. "
    "Use openrecall.server.config_server.ServerSettings or "
    "openrecall.client.config_client.ClientSettings instead.",
    DeprecationWarning,
    stacklevel=2
)
```

- [ ] **Step 2: Keep full backwards compatibility**

The old `Settings` class should continue to work for any code that imports it.

- [ ] **Step 3: Commit**

```bash
git add openrecall/shared/config.py
git commit -m "deprecate(config): mark Settings as deprecated in favor of TOML configs"
```

---

## Task 8: Delete .env Example Files

**Files:**
- Delete: `myrecall_server.env.example`
- Delete: `myrecall_client.env.example`

- [ ] **Step 1: Delete files**

```bash
git rm myrecall_server.env.example myrecall_client.env.example
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore(config): remove deprecated .env.example files"
```

---

## Task 9: Integration Tests

**Files:**
- Create: `tests/test_config_integration.py`

- [ ] **Step 1: Write integration test for TOML loading**

```python
# tests/test_config_integration.py
import pytest
import tempfile
import os
from pathlib import Path

def test_server_settings_loads_from_file():
    """Integration test: ServerSettings loads correctly from TOML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "server.toml"
        config_path.write_text('''
[server]
host = "192.168.1.100"
port = 9000
debug = true

[ai]
provider = "dashscope"
device = "cuda"
''')
        from openrecall.server.config_server import ServerSettings
        settings = ServerSettings.from_toml(config_path)
        
        assert settings.server_host == "192.168.1.100"
        assert settings.server_port == 9000
        assert settings.server_debug == True
        assert settings.ai_provider == "dashscope"
        assert settings.ai_device == "cuda"

def test_client_settings_loads_from_file():
    """Integration test: ClientSettings loads correctly from TOML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "client.toml"
        config_path.write_text('''
[server]
api_url = "http://192.168.1.100:8083/api"
edge_base_url = "http://192.168.1.100:8083"

[dedup]
enabled = false
threshold = 5
''')
        from openrecall.client.config_client import ClientSettings
        settings = ClientSettings.from_toml(config_path)
        
        assert settings.server_api_url == "http://192.168.1.100:8083/api"
        assert settings.dedup_enabled == False
        assert settings.dedup_threshold == 5
        # Defaults preserved
        assert settings.debounce_click_ms == 3000
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_config_integration.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/test_config_integration.py
git commit -m "test(config): add integration tests for TOML config loading"
```

---

## Execution Options

**Plan complete and saved to `docs/superpowers/plans/2026-03-31-toml-config-implementation.md`**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
