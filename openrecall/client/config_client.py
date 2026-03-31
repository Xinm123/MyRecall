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
            stats_interval_sec=data.get("stats.interval_sec", 120),
        )
