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
    ocr_det_db_score_mode: int = 0
    ocr_drop_score: float = 0.0

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
