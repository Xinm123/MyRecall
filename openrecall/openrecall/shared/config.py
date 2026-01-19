"""Configuration management for OpenRecall using pydantic-settings."""

from pathlib import Path

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
    - OPENRECALL_UPLOAD_TIMEOUT: Client upload timeout in seconds
    - OPENRECALL_EMBEDDING_MODEL: Embedding model name for semantic search
    """
    
    debug: bool = Field(default=False, alias="OPENRECALL_DEBUG")
    capture_interval: int = Field(default=30, alias="OPENRECALL_CAPTURE_INTERVAL")
    port: int = Field(default=8083, alias="OPENRECALL_PORT")
    primary_monitor_only: bool = Field(
        default=True, 
        alias="OPENRECALL_PRIMARY_MONITOR_ONLY"
    )
    base_path: Path = Field(
        default_factory=lambda: Path.home() / ".myrecall_data",
        alias="OPENRECALL_DATA_DIR"
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
    embedding_model_name: str = Field(
        default="/Users/tiiny/models/Qwen3-Embedding-0.6B",
        alias="OPENRECALL_EMBEDDING_MODEL",
        description="Embedding model for semantic search"
    )
    embedding_dim: int = Field(
        default=1024,
        alias="OPENRECALL_EMBEDDING_DIM",
        description="Embedding vector dimension (must match model output)"
    )
    
    model_config = {
        "env_prefix": "",
        "populate_by_name": True,
        "extra": "ignore",
    }
    
    @property
    def screenshots_path(self) -> Path:
        """Directory for storing screenshot images."""
        return self.base_path / "screenshots"
    
    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self.base_path / "db" / "recall.db"
    
    @property
    def buffer_path(self) -> Path:
        """Directory for local buffering when server is unavailable."""
        return self.base_path / "buffer"
    
    @property
    def model_cache_path(self) -> Path:
        """Directory for caching ML models."""
        return self.base_path / "models"
    
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
            self.buffer_path,
            self.db_path.parent,
            self.model_cache_path,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @model_validator(mode="after")
    def _ensure_dirs_on_init(self) -> "Settings":
        """Automatically create directories after settings initialization."""
        self.ensure_directories()
        return self


# Global settings instance - directories are created on import
settings = Settings()
