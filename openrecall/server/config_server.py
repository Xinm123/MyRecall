"""Server configuration loaded from server.toml."""

from __future__ import annotations

import logging
import os
import tempfile
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
    ai_request_timeout: int = 120

    # [ocr]
    ocr_provider: str = "rapidocr"
    ocr_model_name: str = ""
    ocr_rapid_version: str = "PP-OCRv4"
    ocr_model_type: str = "mobile"

    # [description] - Independent configuration (no fallback to [ai])
    description_enabled: bool = True
    description_provider: str = "local"  # Default to local provider
    description_model: str = ""
    description_api_key: str = ""
    description_api_base: str = ""

    # [reranker]
    reranker_enabled: bool = False
    reranker_mode: str = "api"
    reranker_url: str = "http://localhost:8083/rerank"
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    reranker_api_key: str = ""

    # [embedding]
    embedding_enabled: bool = True
    embedding_provider: str = "openai"
    embedding_model: str = "qwen3-vl-embedding"
    embedding_api_key: str = ""
    embedding_api_base: str = ""
    embedding_dim: int = 1024

    # [processing]
    processing_mode: str = "ocr"
    processing_queue_capacity: int = 200
    processing_lifo_threshold: int = 10
    processing_preload_models: bool = True

    # [ui]
    ui_show_ai_description: bool = True

    # [advanced]
    fusion_log_enabled: bool = False

    @classmethod
    def _default_filename(cls) -> str:
        """Return default config filename for server."""
        return "server.toml"

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """Create ServerSettings from flat dict (flattened TOML)."""
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
            ai_request_timeout=data.get("ai.request_timeout", 120),
            ocr_provider=data.get("ocr.provider", "rapidocr"),
            ocr_model_name=data.get("ocr.model_name", ""),
            ocr_rapid_version=data.get("ocr.rapid_version", "PP-OCRv4"),
            ocr_model_type=data.get("ocr.model_type", "mobile"),
            description_enabled=data.get("description.enabled", True),
            description_provider=data.get("description.provider", "local"),
            description_model=data.get("description.model", ""),
            description_api_key=data.get("description.api_key", ""),
            description_api_base=data.get("description.api_base", ""),
            reranker_enabled=data.get("reranker.enabled", False),
            reranker_mode=data.get("reranker.mode", "api"),
            reranker_url=data.get("reranker.url", "http://localhost:8083/rerank"),
            reranker_model=data.get("reranker.model", "Qwen/Qwen3-Reranker-0.6B"),
            reranker_api_key=data.get("reranker.api_key", ""),
            embedding_enabled=data.get("embedding.enabled", True),
            embedding_provider=data.get("embedding.provider", "openai"),
            embedding_model=data.get("embedding.model", "qwen3-vl-embedding"),
            embedding_api_key=data.get("embedding.api_key", ""),
            embedding_api_base=data.get("embedding.api_base", ""),
            embedding_dim=data.get("embedding.dim", 1024),
            processing_mode=data.get("processing.mode", "ocr"),
            processing_queue_capacity=data.get("processing.queue_capacity", 200),
            processing_lifo_threshold=data.get("processing.lifo_threshold", 10),
            processing_preload_models=data.get("processing.preload_models", True),
            ui_show_ai_description=data.get("ui.show_ai_description", True),
            fusion_log_enabled=data.get("advanced.fusion_log_enabled", False),
        )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.paths_data_dir = Path(self.paths_data_dir).expanduser().resolve()
        self.paths_cache_dir = Path(self.paths_cache_dir).expanduser().resolve()
        try:
            self.paths_data_dir.mkdir(parents=True, exist_ok=True)
            self.paths_cache_dir.mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "db").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "frames").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "screenshots").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "lancedb").mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.paths_data_dir = Path(tempfile.gettempdir()) / "MRS"
            self.paths_cache_dir = self.paths_data_dir / "cache"
            self.paths_data_dir.mkdir(parents=True, exist_ok=True)
            self.paths_cache_dir.mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "db").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "frames").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "screenshots").mkdir(parents=True, exist_ok=True)
            (self.paths_data_dir / "lancedb").mkdir(parents=True, exist_ok=True)

    @property
    def debug(self) -> bool:
        return self.server_debug

    @property
    def host(self) -> str:
        return self.server_host

    @property
    def port(self) -> int:
        return self.server_port

    @property
    def preload_models(self) -> bool:
        return self.processing_preload_models

    @property
    def queue_capacity(self) -> int:
        return self.processing_queue_capacity

    @property
    def base_path(self) -> Path:
        return self.paths_data_dir

    @property
    def screenshots_path(self) -> Path:
        return self.paths_data_dir / "screenshots"

    @property
    def db_path(self) -> Path:
        return self.paths_data_dir / "db" / "edge.db"

    @property
    def frames_dir(self) -> Path:
        return self.paths_data_dir / "frames"

    @property
    def fts_path(self) -> Path:
        return self.paths_data_dir / "fts.db"

    @property
    def cache_path(self) -> Path:
        return self.paths_cache_dir

    @property
    def model_cache_path(self) -> Path:
        return self.paths_data_dir / "models"

    @property
    def lancedb_path(self) -> Path:
        """Path to the LanceDB directory for embedding storage."""
        return self.paths_data_dir / "lancedb"

    @property
    def ocr_rapid_use_local(self) -> bool:
        return self.ocr_provider == "rapidocr"

    @property
    def device(self) -> str:
        """Alias for ai_device (backward compatibility with old Settings)."""
        return self.ai_device

    @property
    def server_data_dir(self) -> Path:
        """Alias for paths_data_dir (backward compatibility)."""
        return self.paths_data_dir

    @property
    def cache_dir(self) -> Path:
        """Alias for paths_cache_dir (backward compatibility)."""
        return self.paths_cache_dir

    @property
    def ocr_rapid_ocr_version(self) -> str:
        """Alias for ocr_rapid_version (backward compatibility with old config)."""
        return self.ocr_rapid_version

    @property
    def ocr_rapid_model_type(self) -> str:
        """Alias for ocr_model_type (backward compatibility with old config)."""
        return self.ocr_model_type

    def configure_cache_env(self) -> None:
        cache = str(self.paths_cache_dir)
        defaults = {
            "HF_HOME": cache,
            "SENTENCE_TRANSFORMERS_HOME": str(
                self.paths_cache_dir / "sentence_transformers"
            ),
            "TORCH_HOME": str(self.paths_cache_dir / "torch"),
            "DOCTR_CACHE_DIR": str(self.paths_cache_dir / "doctr"),
        }
        for key, value in defaults.items():
            os.environ.setdefault(key, value)
