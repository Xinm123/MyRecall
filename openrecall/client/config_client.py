"""Client configuration loaded from client.toml."""

from __future__ import annotations

import logging
import tempfile
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
    ui_show_ai_description: bool = False

    # [stats]
    stats_interval_sec: int = 120

    @classmethod
    def _default_filename(cls) -> str:
        """Return default config filename for client."""
        return "client.toml"

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """Create ClientSettings from flat dict (flattened TOML)."""
        return cls(
            client_debug=data.get("client.debug", False),
            server_api_url=data.get("server.api_url", "http://localhost:8083/api"),
            server_edge_base_url=data.get(
                "server.edge_base_url", "http://localhost:8083"
            ),
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
            dedup_force_after_skip_seconds=data.get(
                "dedup.force_after_skip_seconds", 30
            ),
            ui_web_enabled=data.get("ui.web_enabled", True),
            ui_web_port=data.get("ui.web_port", 8889),
            ui_show_ai_description=data.get("ui.show_ai_description", False),
            stats_interval_sec=data.get("stats.interval_sec", 120),
        )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.paths_data_dir = Path(self.paths_data_dir).expanduser().resolve()
        self.paths_buffer_dir = Path(self.paths_buffer_dir).expanduser().resolve()
        try:
            self.paths_data_dir.mkdir(parents=True, exist_ok=True)
            self.paths_buffer_dir.mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "screenshots").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "cache").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "spool").mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.paths_data_dir = Path(tempfile.gettempdir()) / "MRC"
            self.paths_buffer_dir = self.paths_data_dir / "buffer"
            self.paths_data_dir.mkdir(parents=True, exist_ok=True)
            self.paths_buffer_dir.mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "screenshots").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "cache").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "spool").mkdir(parents=True, exist_ok=True)

    @property
    def debug(self) -> bool:
        return self.client_debug

    @property
    def show_ai_description(self) -> bool:
        return self.ui_show_ai_description

    @property
    def buffer_path(self) -> Path:
        return self.paths_buffer_dir

    @property
    def spool_path(self) -> Path:
        """Directory for spooling captures before upload (created by SpoolQueue)."""
        return self.paths_data_dir / "spool"

    @property
    def client_screenshots_path(self) -> Path:
        return self.paths_data_dir / "screenshots"

    @property
    def cache_path(self) -> Path:
        return self.paths_data_dir / "cache"

    @property
    def api_url(self) -> str:
        return self.server_api_url

    @property
    def edge_base_url(self) -> str:
        return self.server_edge_base_url

    @property
    def upload_timeout(self) -> int:
        return self.server_upload_timeout

    @property
    def click_debounce_ms(self) -> int:
        return self.debounce_click_ms

    @property
    def trigger_debounce_ms(self) -> int:
        return self.debounce_trigger_ms

    @property
    def capture_debounce_ms(self) -> int:
        return self.debounce_capture_ms

    @property
    def idle_capture_interval_ms(self) -> int:
        return self.debounce_idle_interval_ms

    @property
    def primary_monitor_only(self) -> bool:
        return self.capture_primary_monitor_only

    @property
    def client_web_enabled(self) -> bool:
        return self.ui_web_enabled

    @property
    def client_web_port(self) -> int:
        return self.ui_web_port

    @property
    def client_save_local_screenshots(self) -> bool:
        return self.capture_save_local_copies

    @property
    def simhash_enabled_for_click(self) -> bool:
        return self.dedup_for_click

    @property
    def simhash_enabled_for_app_switch(self) -> bool:
        return self.dedup_for_app_switch

    @property
    def simhash_cache_size_per_device(self) -> int:
        return self.dedup_cache_size_per_device

    @property
    def trigger_queue_capacity(self) -> int:
        return 1000

    @property
    def permission_poll_interval_sec(self) -> int:
        return self.capture_permission_poll_sec

    @property
    def min_capture_interval_ms(self) -> int:
        """Minimum time between any two captures (global debounce)."""
        return self.capture_debounce_ms

    # --- Legacy simhash aliases used by recorder.py (dedup via PHash, not MSSIM) ---

    @property
    def simhash_dedup_enabled(self) -> bool:
        return self.dedup_enabled

    @property
    def simhash_dedup_threshold(self) -> int:
        return self.dedup_threshold

    @property
    def simhash_ttl_seconds(self) -> float:
        return self.dedup_ttl_seconds

    @property
    def max_skip_duration_sec(self) -> int:
        return self.dedup_force_after_skip_seconds

    @property
    def client_data_dir(self) -> Path:
        return self.paths_data_dir
