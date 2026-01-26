"""Configuration management for OpenRecall using pydantic-settings."""

import os
from pathlib import Path
import tempfile

from pydantic import Field, model_validator
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
    """
    
    debug: bool = Field(default=True, alias="OPENRECALL_DEBUG")
    capture_interval: int = Field(default=10, alias="OPENRECALL_CAPTURE_INTERVAL")
    host: str = Field(default="127.0.0.1", alias="OPENRECALL_HOST")
    port: int = Field(default=8083, alias="OPENRECALL_PORT")
    primary_monitor_only: bool = Field(
        default=True, 
        alias="OPENRECALL_PRIMARY_MONITOR_ONLY"
    )
    base_path: Path = Field(
        default_factory=lambda: Path.home() / ".openrecall" / "data",
        alias="OPENRECALL_DATA_DIR"
    )
    cache_dir: Path | None = Field(
        default=None,
        alias="OPENRECALL_CACHE_DIR",
        description="Optional override for cache directory (HF/Transformers/Doctr/Torch caches)"
    )
    client_screenshots_dir: Path | None = Field(
        default=None,
        alias="OPENRECALL_CLIENT_SCREENSHOTS_DIR",
        description="Optional override for client local screenshots directory"
    )
    api_url: str = Field(
        default="http://localhost:8083/api",
        alias="OPENRECALL_API_URL"
    )
    device: str = Field(
        default="cpu",
        alias="OPENRECALL_DEVICE",
        description="Device for AI inference (cpu, cuda, mps)"
    )
    upload_timeout: int = Field(
        default=180,
        alias="OPENRECALL_UPLOAD_TIMEOUT",
        description="Client upload timeout in seconds (needs to be long for CPU AI inference)"
    )
    preload_models: bool = Field(
        default=True,
        alias="OPENRECALL_PRELOAD_MODELS",
        description="Preload AI models at startup to avoid first-request latency"
    )
    ai_provider: str = Field(
        default="local",
        alias="OPENRECALL_AI_PROVIDER",
        description="AI provider for vision analysis (local, dashscope, openai)"
    )
    ai_model_name: str = Field(
        default="",
        alias="OPENRECALL_AI_MODEL_NAME",
        description="Model name/path for the selected AI provider"
    )
    ai_api_key: str = Field(
        default="",
        alias="OPENRECALL_AI_API_KEY",
        description="API key for cloud AI providers"
    )
    ai_api_base: str = Field(
        default="",
        alias="OPENRECALL_AI_API_BASE",
        description="Optional base URL for OpenAI-compatible proxies (DeepSeek/vLLM/etc.)"
    )
    vision_provider: str = Field(
        default="",
        alias="OPENRECALL_VISION_PROVIDER",
        description="Optional override for vision provider; falls back to ai_provider when empty"
    )
    vision_model_name: str = Field(
        default="",
        alias="OPENRECALL_VISION_MODEL_NAME",
        description="Optional override for vision model name/path; falls back to ai_model_name when empty"
    )
    vision_api_key: str = Field(
        default="",
        alias="OPENRECALL_VISION_API_KEY",
        description="Optional override for vision API key; falls back to ai_api_key when empty"
    )
    vision_api_base: str = Field(
        default="",
        alias="OPENRECALL_VISION_API_BASE",
        description="Optional override for vision API base URL; falls back to ai_api_base when empty"
    )
    ocr_provider: str = Field(
        default="",
        alias="OPENRECALL_OCR_PROVIDER",
        description="Optional override for OCR provider; falls back to ai_provider when empty"
    )
    ocr_model_name: str = Field(
        default="",
        alias="OPENRECALL_OCR_MODEL_NAME",
        description="Optional override for OCR model name; falls back to ai_model_name when empty"
    )
    ocr_api_key: str = Field(
        default="",
        alias="OPENRECALL_OCR_API_KEY",
        description="Optional override for OCR API key; falls back to ai_api_key when empty"
    )
    ocr_api_base: str = Field(
        default="",
        alias="OPENRECALL_OCR_API_BASE",
        description="Optional override for OCR API base URL; falls back to ai_api_base when empty"
    )
    embedding_provider: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_PROVIDER",
        description="Optional override for embedding provider; falls back to ai_provider when empty"
    )
    embedding_api_model_name: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_MODEL_NAME",
        description="Optional override for embedding API model; falls back to ai_model_name when empty"
    )
    embedding_api_key: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_API_KEY",
        description="Optional override for embedding API key; falls back to ai_api_key when empty"
    )
    embedding_api_base: str = Field(
        default="",
        alias="OPENRECALL_EMBEDDING_API_BASE",
        description="Optional override for embedding API base URL; falls back to ai_api_base when empty"
    )
    embedding_model_name: str = Field(
        default="qwen-text-v1",
        alias="OPENRECALL_EMBEDDING_MODEL",
        description="Embedding model for semantic search"
    )
    keyword_strategy: str = Field(
        default="local",
        alias="OPENRECALL_KEYWORD_STRATEGY",
        description="Strategy for keyword extraction (local, rake, etc.)"
    )
    embedding_dim: int = Field(
        default=1024,
        alias="OPENRECALL_EMBEDDING_DIM",
        description="Embedding vector dimension (must match model output)"
    )
    processing_lifo_threshold: int = Field(
        default=10,
        alias="OPENRECALL_PROCESSING_LIFO_THRESHOLD",
        description="When pending tasks > threshold, use LIFO (newest first) instead of FIFO"
    )
    show_ai_description: bool = Field(
        default=True,
        alias="OPENRECALL_SHOW_AI_DESCRIPTION",
        description="Toggle visibility of AI text on the frontend"
    )
    user_idle_threshold_seconds: int = Field(
        default=60,
        alias="OPENRECALL_USER_IDLE_THRESHOLD_SECONDS",
        description="Consider user inactive if idle time exceeds this threshold (seconds)"
    )
    similarity_threshold: float = Field(
        default=0.98,
        alias="OPENRECALL_SIMILARITY_THRESHOLD",
        description="MSSIM threshold; higher captures more (images considered similar when MSSIM >= threshold)"
    )
    disable_similarity_filter: bool = Field(
        default=False,
        alias="OPENRECALL_DISABLE_SIMILARITY_FILTER",
        description="Disable similarity-based deduplication and capture every cycle"
    )
    client_save_local_screenshots: bool = Field(
        default=False,
        alias="OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS",
        description="Whether the client saves local screenshots (WebP) in addition to buffering/uploading"
    )
    
    model_config = {
        "env_prefix": "",
        "populate_by_name": True,
        "extra": "ignore",
        "env_file": ["openrecall.env", ".env"],
        "env_file_encoding": "utf-8",
    }
    
    @property
    def screenshots_path(self) -> Path:
        """Directory for storing screenshot images."""
        return self.base_path / "screenshots"

    @property
    def client_screenshots_path(self) -> Path:
        """Directory for storing client local screenshots.
        
        Defaults to screenshots_path for backwards compatibility.
        """
        return self.client_screenshots_dir or self.screenshots_path
    
    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self.base_path / "db" / "recall.db"

    @property
    def lancedb_path(self) -> Path:
        """Path to the LanceDB directory."""
        return self.base_path / "lancedb"

    @property
    def fts_path(self) -> Path:
        """Path to the SQLite FTS database file."""
        return self.base_path / "fts.db"
    
    @property
    def buffer_path(self) -> Path:
        """Directory for local buffering when server is unavailable."""
        return self.base_path / "buffer"
    
    @property
    def model_cache_path(self) -> Path:
        """Directory for caching ML models."""
        return self.base_path / "models"

    @property
    def cache_path(self) -> Path:
        return self.cache_dir or (self.base_path / "cache")
    
    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist.
        
        This method ensures that:
        - base_path exists
        - screenshots_path exists
        - buffer_path exists
        - Parent directory of db_path exists
        - model_cache_path exists
        """
        directories = [
            self.base_path,
            self.screenshots_path,
            self.client_screenshots_path,
            self.buffer_path,
            self.db_path.parent,
            self.model_cache_path,
            self.cache_path,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def verify_writable(self) -> None:
        test_path = self.base_path / ".write_test"
        test_path.write_bytes(b"ok")
        test_path.unlink(missing_ok=True)
    
    def configure_cache_env(self) -> None:
        cache = str(self.cache_path)
        defaults = {
            "HF_HOME": cache,
            "SENTENCE_TRANSFORMERS_HOME": str(self.cache_path / "sentence_transformers"),
            "TORCH_HOME": str(self.cache_path / "torch"),
            "DOCTR_CACHE_DIR": str(self.cache_path / "doctr"),
        }
        for key, value in defaults.items():
            os.environ.setdefault(key, value)

    @model_validator(mode="after")
    def _ensure_dirs_on_init(self) -> "Settings":
        """Automatically create directories after settings initialization."""
        try:
            self.ensure_directories()
            self.verify_writable()
        except PermissionError:
            self.base_path = Path(tempfile.gettempdir()) / "myrecall_data"
            self.ensure_directories()
            self.verify_writable()
        self.configure_cache_env()
        return self


# Global settings instance - directories are created on import
settings = Settings()
