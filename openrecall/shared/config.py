"""Configuration management for OpenRecall using pydantic-settings."""

import os
from typing import Optional, Union
from pathlib import Path
import tempfile

from pydantic import Field, model_validator, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with automatic directory creation.

    Settings can be configured via environment variables:
    - OPENRECALL_DEBUG: Enable debug mode (verbose logging)
    - OPENRECALL_DATA_DIR: Base directory for all data storage
    - OPENRECALL_PORT: Web server port
    - OPENRECALL_PRIMARY_MONITOR_ONLY: Only record primary monitor
    - OPENRECALL_API_URL: Server API URL for client communication
    - OPENRECALL_CAPTURE_INTERVAL: Screenshot capture interval in seconds
    - OPENRECALL_DEVICE: Device for AI inference (cpu, cuda, mps)
    - OPENRECALL_AI_PROVIDER: AI provider for vision analysis (local, dashscope, openai)
    - OPENRECALL_AI_MODEL_NAME: Model name/path for the selected AI provider
    - OPENRECALL_AI_API_KEY: API key for cloud AI providers
    - OPENRECALL_AI_API_BASE: Optional base URL for OpenAI-compatible proxies
    - OPENRECALL_VISION_PROVIDER: Optional override for vision provider (falls back to OPENRECALL_AI_PROVIDER)
    - OPENRECALL_VISION_MODEL_NAME: Optional override for vision model name/path
    - OPENRECALL_VISION_API_KEY: Optional override for vision API key
    - OPENRECALL_VISION_API_BASE: Optional override for vision API base URL
    - OPENRECALL_OCR_PROVIDER: Optional override for OCR provider (falls back to OPENRECALL_AI_PROVIDER)
    - OPENRECALL_OCR_MODEL_NAME: Optional override for OCR model name (for API-based OCR)
    - OPENRECALL_OCR_API_KEY: Optional override for OCR API key
    - OPENRECALL_OCR_API_BASE: Optional override for OCR API base URL
    - OPENRECALL_EMBEDDING_PROVIDER: Optional override for embedding provider (falls back to OPENRECALL_AI_PROVIDER)
    - OPENRECALL_EMBEDDING_MODEL_NAME: Optional override for embedding model name (for API embeddings)
    - OPENRECALL_EMBEDDING_API_KEY: Optional override for embedding API key
    - OPENRECALL_EMBEDDING_API_BASE: Optional override for embedding API base URL
    - OPENRECALL_UPLOAD_TIMEOUT: Client upload timeout in seconds
    - OPENRECALL_EMBEDDING_MODEL: Embedding model name for semantic search
    - OPENRECALL_CLIENT_WEB_PORT: Port for client web UI server
    - OPENRECALL_CLIENT_WEB_ENABLED: Enable client web UI server
    - OPENRECALL_EDGE_BASE_URL: Base URL for Edge API server (used by client web UI)
    - OPENRECALL_CLIENT_CORS_ORIGIN: Allowed CORS origin for Edge server
    """

    debug: bool = Field(default=True, alias="OPENRECALL_DEBUG")
    capture_interval: int = Field(default=10, alias="OPENRECALL_CAPTURE_INTERVAL")

    # Three-layer debounce configuration (separate control for each layer)
    click_debounce_ms: int = Field(
        default=3000,
        alias="OPENRECALL_CLICK_DEBOUNCE_MS",
        description="Debounce interval for CLICK events (Layer 1: LockFreeDebouncer in CGEventTap thread)",
    )
    trigger_debounce_ms: int = Field(
        default=3000,
        alias="OPENRECALL_TRIGGER_DEBOUNCE_MS",
        description="Debounce interval for APP_SWITCH/IDLE/MANUAL events (Layer 2: TriggerDebouncer)",
    )
    capture_debounce_ms: int = Field(
        default=3000,
        alias="OPENRECALL_CAPTURE_DEBOUNCE_MS",
        description="Global debounce in capture loop (Layer 3: prevents duplicate captures from concurrent triggers)",
    )

    idle_capture_interval_ms: int = Field(
        default=60000,
        alias="OPENRECALL_IDLE_CAPTURE_INTERVAL_MS",
        description="Idle fallback interval in milliseconds for capture_trigger=idle",
    )
    permission_poll_interval_sec: int = Field(
        default=10,
        alias="OPENRECALL_PERMISSION_POLL_INTERVAL_SEC",
        description="Polling interval for capture permission state checks",
    )
    trigger_queue_capacity: int = Field(
        default=1000,
        alias="OPENRECALL_TRIGGER_QUEUE_CAPACITY",
        description="Capacity of the bounded trigger event queue (aligned with screenpipe max_buffer_size scale)",
    )
    stats_interval_sec: int = Field(
        default=120,
        alias="OPENRECALL_STATS_INTERVAL_SEC",
        description="Statistics logging interval in seconds",
    )
    host: str = Field(default="127.0.0.1", alias="OPENRECALL_HOST")
    port: int = Field(default=8083, alias="OPENRECALL_PORT")
    primary_monitor_only: bool = Field(
        default=True, alias="OPENRECALL_PRIMARY_MONITOR_ONLY"
    )

    # Split Data Directories
    server_data_dir: Path = Field(
        default_factory=lambda: Path.home() / "MRS",
        alias="OPENRECALL_SERVER_DATA_DIR",
        description="Base directory for server data (DB, Vector Store, Server Screenshots)",
    )
    client_data_dir: Path = Field(
        default_factory=lambda: Path.home() / "MRC",
        alias="OPENRECALL_CLIENT_DATA_DIR",
        description="Base directory for client data (Buffer, Local Screenshots)",
    )

    # Legacy base_path field - mapped to server_data_dir for backward compatibility if not overridden
    # We keep it as a field because Pydantic might try to populate it from env OPENRECALL_DATA_DIR
    base_path_legacy: Optional[Path] = Field(default=None, alias="OPENRECALL_DATA_DIR")

    cache_dir: Optional[Path] = Field(
        default=None,
        alias="OPENRECALL_CACHE_DIR",
        description="Optional override for cache directory (HF/Transformers/Doctr/Torch caches)",
    )
    client_screenshots_dir: Optional[Path] = Field(
        default=None,
        alias="OPENRECALL_CLIENT_SCREENSHOTS_DIR",
        description="Optional override for client local screenshots directory",
    )
    api_url: str = Field(
        default="http://localhost:8083/api", alias="OPENRECALL_API_URL"
    )
    device: str = Field(
        default="cpu",
        alias="OPENRECALL_DEVICE",
        description="Device for AI inference (cpu, cuda, mps)",
    )
    upload_timeout: int = Field(
        default=180,
        alias="OPENRECALL_UPLOAD_TIMEOUT",
        description="Client upload timeout in seconds (needs to be long for CPU AI inference)",
    )
    ai_request_timeout: int = Field(
        default=120,
        alias="OPENRECALL_AI_REQUEST_TIMEOUT",
        description="Timeout for AI provider requests in seconds",
    )
    preload_models: bool = Field(
        default=True,
        alias="OPENRECALL_PRELOAD_MODELS",
        description="Preload AI models at startup to avoid first-request latency",
    )
    ai_provider: str = Field(
        default="local",
        alias="OPENRECALL_AI_PROVIDER",
        description="AI provider for vision analysis (local, dashscope, openai)",
    )
    ai_model_name: str = Field(
        default="",
        alias="OPENRECALL_AI_MODEL_NAME",
        description="Model name/path for the selected AI provider",
    )
    ai_api_key: str = Field(
        default="",
        alias="OPENRECALL_AI_API_KEY",
        description="API key for cloud AI providers",
    )
    ai_api_base: str = Field(
        default="",
        alias="OPENRECALL_AI_API_BASE",
        description="Optional base URL for OpenAI-compatible proxies (DeepSeek/vLLM/etc.)",
    )
    vision_provider: str = Field(
        default="",
        alias="OPENRECALL_VISION_PROVIDER",
        description="Optional override for vision provider; falls back to ai_provider when empty",
    )
    vision_model_name: str = Field(
        default="",
        alias="OPENRECALL_VISION_MODEL_NAME",
        description="Optional override for vision model name/path; falls back to ai_model_name when empty",
    )
    vision_api_key: str = Field(
        default="",
        alias="OPENRECALL_VISION_API_KEY",
        description="Optional override for vision API key; falls back to ai_api_key when empty",
    )
    vision_api_base: str = Field(
        default="",
        alias="OPENRECALL_VISION_API_BASE",
        description="Optional override for vision API base URL; falls back to ai_api_base when empty",
    )
    ocr_provider: str = Field(
        default="",
        alias="OPENRECALL_OCR_PROVIDER",
        description="Optional override for OCR provider; falls back to ai_provider when empty",
    )
    ocr_model_name: str = Field(
        default="",
        alias="OPENRECALL_OCR_MODEL_NAME",
        description="Optional override for OCR model name; falls back to ai_model_name when empty",
    )
    ocr_api_key: str = Field(
        default="",
        alias="OPENRECALL_OCR_API_KEY",
        description="Optional override for OCR API key; falls back to ai_api_key when empty",
    )
    ocr_api_base: str = Field(
        default="",
        alias="OPENRECALL_OCR_API_BASE",
        description="Optional override for OCR API base URL; falls back to ai_api_base when empty",
    )

    # RapidOCR v3 API 配置参数
    # 模型默认随 pip 包安装，首次使用无需下载（PP-OCRv4）
    ocr_rapid_ocr_version: str = Field(
        default="PP-OCRv4",
        alias="OPENRECALL_OCR_RAPID_OCR_VERSION",
        description="OCR model version: PP-OCRv4 (default, bundled with pip), PP-OCRv5 (requires first-use download)",
    )
    ocr_rapid_model_type: str = Field(
        default="mobile",
        alias="OPENRECALL_OCR_RAPID_MODEL_TYPE",
        description="Model size: mobile (fast, lightweight) or server (accurate, heavier)",
    )

    # OCR 质量调优参数 (P1-S3+ 质量优化)
    # 文档: https://www.paddleocr.ai/v2.9/en/ppocr/blog/inference_args.html
    ocr_det_db_thresh: float = Field(
        default=0.3,
        alias="OPENRECALL_OCR_DET_DB_THRESH",
        description=(
            "DB检测算法的像素级文本概率阈值。"
            "概率图中仅大于此阈值的像素才被视为文本像素。"
            "调大：减少误识别（非文字区域被识别为文字），但可能漏检淡色/模糊文字。"
            "调小：检测更多淡色文字，但增加误识别风险。"
            "推荐范围: 0.2-0.4，默认 0.3"
        ),
    )
    ocr_det_db_box_thresh: float = Field(
        default=0.7,
        alias="OPENRECALL_OCR_DET_DB_BOX_THRESH",
        description=(
            "DB检测算法的文本框置信度阈值。"
            "检测框内所有像素的平均分数大于此阈值时，才认为是文本区域。"
            "调大：减少误识别（过滤低置信度框），提高精确率，但可能漏检边缘文字。"
            "调小：检测更多文本区域，提高召回率，但增加误识别。"
            "推荐范围: 0.5-0.8，默认 0.7（高于 PaddleOCR 原默认 0.6 以减少误识别）"
        ),
    )
    ocr_det_db_unclip_ratio: float = Field(
        default=1.6,
        alias="OPENRECALL_OCR_DET_DB_UNCLIP_RATIO",
        description=(
            "DB检测算法的文本框扩展比例（Vatti clipping 算法）。"
            "用于扩展检测到的文本框边界，确保文字完整。"
            "调大：文本框更大，包含更多上下文，适合字间距大的场景，但可能框入相邻文字或非文字区域。"
            "调小：文本框更紧凑，适合密集文字，但可能截断文字边缘。"
            "推荐范围: 1.5-2.0，默认 1.6"
        ),
    )
    ocr_det_db_score_mode: str = Field(
        default="slow",
        alias="OPENRECALL_OCR_DET_DB_SCORE_MODE",
        description=(
            "DB检测算法的置信度计算方式。"
            "'fast': 使用边界矩形内所有像素计算平均分，速度快但不够精确。"
            "'slow': 使用原始多边形内所有像素计算平均分，更精确但稍慢。"
            "推荐使用 'slow' 以获得更准确的文本框过滤，减少误识别。"
        ),
    )
    ocr_drop_score: float = Field(
        default=0.6,
        alias="OPENRECALL_OCR_DROP_SCORE",
        description=(
            "识别结果置信度过滤阈值。"
            "识别分数低于此阈值的结果将被丢弃，不返回。"
            "调大：只保留高置信度识别结果，减少错误识别，但可能丢弃正确但低置信度的文字。"
            "调小：保留更多识别结果，提高召回率，但增加错误识别。"
            "推荐范围: 0.4-0.7，默认 0.6（高于 PaddleOCR 原默认 0.5 以减少错误识别）"
        ),
    )
    ocr_det_limit_side_len: int = Field(
        default=960,
        alias="OPENRECALL_OCR_DET_LIMIT_SIDE_LEN",
        description=(
            "检测图像边长限制。"
            "图像最长边超过此值时会缩放，以控制计算量。"
            "调大：检测更精细，适合高分辨率大图，但处理更慢。"
            "调小：处理更快，但可能漏检小字或细节。"
            "推荐范围: 640-1920，默认 960"
        ),
    )
    embedding_provider: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_PROVIDER",
        description="Optional override for embedding provider; falls back to ai_provider when empty",
    )
    embedding_api_model_name: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_MODEL_NAME",
        description="Optional override for embedding API model; falls back to ai_model_name when empty",
    )
    embedding_api_key: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_API_KEY",
        description="Optional override for embedding API key; falls back to ai_api_key when empty",
    )
    embedding_api_base: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_API_BASE",
        description="Optional override for embedding API base URL; falls back to ai_api_base when empty",
    )
    embedding_model_name: str = Field(
        default="qwen-text-v1",
        alias="OPENRECALL_EMBEDDING_MODEL",
        description="Embedding model for semantic search",
    )

    # Description generation settings
    description_enabled: bool = Field(
        default=True,
        alias="OPENRECALL_DESCRIPTION_ENABLED",
        description="Enable AI description generation for frames",
    )
    description_provider: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_DESCRIPTION_PROVIDER",
        description="Optional override for description provider; falls back to ai_provider when empty",
    )
    description_model: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_DESCRIPTION_MODEL",
        description="Optional override for description model name/path; falls back to ai_model_name when empty",
    )
    description_api_key: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_DESCRIPTION_API_KEY",
        description="Optional override for description API key; falls back to ai_api_key when empty",
    )
    description_api_base: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_DESCRIPTION_API_BASE",
        description="Optional override for description API base URL; falls back to ai_api_base when empty",
    )

    keyword_strategy: str = Field(
        default="local",
        alias="OPENRECALL_KEYWORD_STRATEGY",
        description="Strategy for keyword extraction (local, rake, etc.)",
    )
    embedding_dim: int = Field(
        default=1024,
        alias="OPENRECALL_EMBEDDING_DIM",
        description="Embedding vector dimension (must match model output)",
    )

    # v3 Ingestion Configuration
    processing_mode: str = Field(
        default="ocr",
        alias="OPENRECALL_PROCESSING_MODE",
        description="Processing mode for frame ingestion: 'ocr' (default), 'noop' for testing/debugging, or 'legacy' for old AI pipeline",
    )
    queue_capacity: int = Field(
        default=200,
        alias="OPENRECALL_QUEUE_CAPACITY",
        description="Maximum number of pending frames in the queue",
    )

    # Reranker Configuration
    reranker_mode: str = Field(
        default="api",
        alias="OPENRECALL_RERANKER_MODE",
        description="Reranker mode: 'api' or 'local'",
    )
    reranker_url: str = Field(
        default="http://localhost:8080/rerank",
        alias="OPENRECALL_RERANKER_URL",
        description="URL for the reranker API (compatible with TEI/BGE)",
    )
    reranker_model: str = Field(
        default="Qwen/Qwen3-Reranker-0.6B",
        alias="OPENRECALL_RERANKER_MODEL",
        description="Model name/path for the reranker",
    )
    reranker_api_key: str = Field(
        default="",
        alias="OPENRECALL_RERANKER_API_KEY",
        description="Optional API key specifically for the reranker service",
    )

    processing_lifo_threshold: int = Field(
        default=10,
        alias="OPENRECALL_PROCESSING_LIFO_THRESHOLD",
        description="When pending tasks > threshold, use LIFO (newest first) instead of FIFO",
    )
    show_ai_description: bool = Field(
        default=True,
        alias="OPENRECALL_SHOW_AI_DESCRIPTION",
        description="Toggle visibility of AI text on the frontend",
    )
    user_idle_threshold_seconds: int = Field(
        default=60,
        alias="OPENRECALL_USER_IDLE_THRESHOLD_SECONDS",
        description="Consider user inactive if idle time exceeds this threshold (seconds)",
    )
    similarity_threshold: float = Field(
        default=0.98,
        alias="OPENRECALL_SIMILARITY_THRESHOLD",
        description="MSSIM threshold; higher captures more (images considered similar when MSSIM >= threshold)",
    )
    disable_similarity_filter: bool = Field(
        default=False,
        alias="OPENRECALL_DISABLE_SIMILARITY_FILTER",
        description="Disable similarity-based deduplication and capture every cycle",
    )

    # PHash-based Similarity Detection (P1-S2b+)
    simhash_dedup_enabled: bool = Field(
        default=True,
        alias="OPENRECALL_SIMHASH_DEDUP_ENABLED",
        description="Enable PHash-based similarity detection to drop redundant frames",
    )
    simhash_dedup_threshold: int = Field(
        default=10,
        ge=0,
        le=64,
        alias="OPENRECALL_SIMHASH_DEDUP_THRESHOLD",
        description="Maximum Hamming distance for PHash similarity (0-64 bits). Default 10 aligns with screenpipe.",
    )
    simhash_ttl_seconds: float = Field(
        default=60.0,
        alias="OPENRECALL_SIMHASH_TTL_SECONDS",
        description="TTL in seconds for simhash cache entries. After TTL, similar content is captured.",
    )
    simhash_cache_size_per_device: int = Field(
        default=1,
        alias="OPENRECALL_SIMHASH_CACHE_SIZE",
        description="Number of recent PHash values to cache per device for similarity checks",
    )
    simhash_enabled_for_click: bool = Field(
        default=True,
        alias="OPENRECALL_SIMHASH_ENABLED_FOR_CLICK",
        description="Enable simhash dedup for click triggers (idle always skips simhash)",
    )
    simhash_enabled_for_app_switch: bool = Field(
        default=False,
        alias="OPENRECALL_SIMHASH_ENABLED_FOR_APP_SWITCH",
        description="Enable simhash dedup for app_switch triggers (idle always skips simhash)",
    )
    max_skip_duration_sec: int = Field(
        default=30,
        alias="OPENRECALL_MAX_SKIP_DURATION_SEC",
        description="Force capture after this many seconds of skipped frames (safety valve for simhash)",
    )
    client_save_local_screenshots: bool = Field(
        default=False,
        alias="OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS",
        description="Whether the client saves local screenshots (WebP) in addition to buffering/uploading",
    )
    fusion_log_enabled: bool = Field(
        default=False,
        alias="OPENRECALL_FUSION_LOG_ENABLED",
        description="Whether to log fusion text to a file for debugging",
    )
    # Client Web UI Configuration
    client_web_port: int = Field(
        default=8883,
        alias="OPENRECALL_CLIENT_WEB_PORT",
        description="Port for client web UI server",
    )
    client_web_enabled: bool = Field(
        default=True,
        alias="OPENRECALL_CLIENT_WEB_ENABLED",
        description="Enable client web UI server",
    )
    edge_base_url: str = Field(
        default="http://localhost:8083",
        alias="OPENRECALL_EDGE_BASE_URL",
        description="Base URL for Edge API server (used by client web UI)",
    )
    client_cors_origin: str = Field(
        default="http://localhost:8883",
        alias="OPENRECALL_CLIENT_CORS_ORIGIN",
        description="Allowed CORS origin for Edge server (client web UI origin)",
    )

    @field_validator(
        "server_data_dir",
        "client_data_dir",
        "cache_dir",
        "client_screenshots_dir",
        "base_path_legacy",
        mode="before",
    )
    @classmethod
    def expand_path(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        if v is None:
            return None
        return Path(str(v)).expanduser().resolve()

    model_config = {
        "env_prefix": "",
        "populate_by_name": True,
        "extra": "ignore",
        "env_file": ["openrecall.env", ".env"],
        "env_file_encoding": "utf-8",
    }

    @property
    def base_path(self) -> Path:
        """Backward compatibility for base_path, defaulting to server_data_dir."""
        if self.base_path_legacy:
            return self.base_path_legacy
        return self.server_data_dir

    @property
    def screenshots_path(self) -> Path:
        """Directory for storing screenshot images (Server side)."""
        return self.server_data_dir / "screenshots"

    @property
    def client_screenshots_path(self) -> Path:
        """Directory for storing client local screenshots.

        Defaults to client_data_dir/screenshots.
        """
        return self.client_screenshots_dir or (self.client_data_dir / "screenshots")

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file (v3: edge.db)."""
        return self.server_data_dir / "db" / "edge.db"

    @property
    def frames_dir(self) -> Path:
        """Directory for storing frame snapshots."""
        return self.server_data_dir / "frames"

    @property
    def lancedb_path(self) -> Path:
        """Path to the LanceDB directory."""
        return self.server_data_dir / "lancedb"

    @property
    def fts_path(self) -> Path:
        """Path to the SQLite FTS database file."""
        return self.server_data_dir / "fts.db"

    @property
    def buffer_path(self) -> Path:
        """Directory for local buffering when server is unavailable."""
        return self.client_data_dir / "buffer"

    @property
    def spool_path(self) -> Path:
        """Directory for spooling captures before upload."""
        return self.client_data_dir / "spool"

    @property
    def model_cache_path(self) -> Path:
        """Directory for caching ML models."""
        return self.server_data_dir / "models"

    @property
    def cache_path(self) -> Path:
        return self.cache_dir or (self.server_data_dir / "cache")

    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        directories = [
            self.server_data_dir,
            self.client_data_dir,
            self.screenshots_path,
            self.client_screenshots_path,
            self.buffer_path,
            self.spool_path,
            self.db_path.parent,
            self.frames_dir,
            self.lancedb_path,
            self.model_cache_path,
            self.cache_path,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def verify_writable(self) -> None:
        for path in [self.server_data_dir, self.client_data_dir]:
            test_path = path / ".write_test"
            test_path.write_bytes(b"ok")
            test_path.unlink(missing_ok=True)

    def configure_cache_env(self) -> None:
        cache = str(self.cache_path)
        defaults = {
            "HF_HOME": cache,
            "SENTENCE_TRANSFORMERS_HOME": str(
                self.cache_path / "sentence_transformers"
            ),
            "TORCH_HOME": str(self.cache_path / "torch"),
            "DOCTR_CACHE_DIR": str(self.cache_path / "doctr"),
        }
        for key, value in defaults.items():
            os.environ.setdefault(key, value)

    @model_validator(mode="after")
    def _ensure_dirs_on_init(self) -> "Settings":
        """Automatically create directories after settings initialization."""
        if "OPENRECALL_IDLE_CAPTURE_INTERVAL_MS" not in os.environ:
            legacy_capture_interval = os.environ.get("OPENRECALL_CAPTURE_INTERVAL")
            if legacy_capture_interval:
                self.idle_capture_interval_ms = int(legacy_capture_interval) * 1000

        try:
            self.ensure_directories()
            self.verify_writable()
        except PermissionError:
            # Fallback for permission errors - maybe just use temp for both?
            # Or log warning. For now, let's just try to fallback base_path logic if it was used,
            # but here we have explicit paths.
            # If server dir fails, fallback to temp/MRS. If client fails, temp/MRC.
            if not os.access(self.server_data_dir.parent, os.W_OK):
                self.server_data_dir = Path(tempfile.gettempdir()) / "MRS"
            if not os.access(self.client_data_dir.parent, os.W_OK):
                self.client_data_dir = Path(tempfile.gettempdir()) / "MRC"

            self.ensure_directories()
            self.verify_writable()

        self.configure_cache_env()
        return self


# Global settings instance - directories are created on import
settings = Settings()
