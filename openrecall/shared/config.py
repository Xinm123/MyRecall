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
    - OPENRECALL_VIDEO_MONITOR_IDS: Comma-separated monitor IDs for monitor-id recording
    - OPENRECALL_VIDEO_PIPELINE_RESTART_ON_PROFILE_CHANGE: Restart pipeline on profile change
    - OPENRECALL_VIDEO_POOL_MAX_BYTES: Max persistent frame buffer size per monitor
    - OPENRECALL_VIDEO_SEGMENT_STAGGER_SECONDS: Startup stagger for multi-monitor pipelines
    - OPENRECALL_VIDEO_PIPE_WRITE_WARN_MS: Warn threshold for ffmpeg stdin write latency
    - OPENRECALL_VIDEO_PIPELINE_MODE: Video pipeline mode (segment|chunk_process)
    - OPENRECALL_VIDEO_PIPE_WRITE_TIMEOUT_MS: Timeout for single ffmpeg stdin write (ms)
    - OPENRECALL_VIDEO_NO_CHUNK_PROGRESS_TIMEOUT_SECONDS: Segment-mode chunk boundary no-progress timeout
    - OPENRECALL_VIDEO_COLOR_RANGE: Raw input color range policy (auto|tv|pc)
    - OPENRECALL_SCK_START_RETRY_MAX: Max short-retry count before degrading to legacy mode
    - OPENRECALL_SCK_RETRY_BACKOFF_SECONDS: Backoff seconds between short SCK retries
    - OPENRECALL_SCK_PERMISSION_BACKOFF_SECONDS: Backoff seconds after permission denied
    - OPENRECALL_SCK_RECOVERY_PROBE_SECONDS: Probe interval to recover from legacy to SCK
    - OPENRECALL_SCK_AUTO_RECOVER_FROM_LEGACY: Whether to auto-probe and recover to SCK
    """
    
    debug: bool = Field(default=True, alias="OPENRECALL_DEBUG")
    capture_interval: int = Field(default=10, alias="OPENRECALL_CAPTURE_INTERVAL")
    host: str = Field(default="127.0.0.1", alias="OPENRECALL_HOST")
    port: int = Field(default=8083, alias="OPENRECALL_PORT")
    primary_monitor_only: bool = Field(
        default=True, 
        alias="OPENRECALL_PRIMARY_MONITOR_ONLY"
    )
    
    # Split Data Directories
    server_data_dir: Path = Field(
        default_factory=lambda: Path.home() / "MRS",
        alias="OPENRECALL_SERVER_DATA_DIR",
        description="Base directory for server data (DB, Vector Store, Server Screenshots)"
    )
    client_data_dir: Path = Field(
        default_factory=lambda: Path.home() / "MRC",
        alias="OPENRECALL_CLIENT_DATA_DIR",
        description="Base directory for client data (Buffer, Local Screenshots)"
    )
    
    # Legacy base_path field - mapped to server_data_dir for backward compatibility if not overridden
    # We keep it as a field because Pydantic might try to populate it from env OPENRECALL_DATA_DIR
    base_path_legacy: Optional[Path] = Field(
        default=None,
        alias="OPENRECALL_DATA_DIR"
    )

    cache_dir: Optional[Path] = Field(
        default=None,
        alias="OPENRECALL_CACHE_DIR",
        description="Optional override for cache directory (HF/Transformers/Doctr/Torch caches)"
    )
    client_screenshots_dir: Optional[Path] = Field(
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
    ai_request_timeout: int = Field(
        default=120,
        alias="OPENRECALL_AI_REQUEST_TIMEOUT",
        description="Timeout for AI provider requests in seconds"
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
    ocr_rapid_use_local: bool = Field(
        default=False,
        alias="OPENRECALL_OCR_RAPID_USE_LOCAL",
        description="Whether to use local models for RapidOCR"
    )
    ocr_rapid_model_dir: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_OCR_RAPID_MODEL_DIR",
        description="Directory containing RapidOCR models (required if use_local is True)"
    )
    ocr_rapid_det_model: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_OCR_RAPID_DET_MODEL",
        description="Path to RapidOCR detection model"
    )
    ocr_rapid_rec_model: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_OCR_RAPID_REC_MODEL",
        description="Path to RapidOCR recognition model"
    )
    ocr_rapid_cls_model: Optional[str] = Field(
        default=None,
        alias="OPENRECALL_OCR_RAPID_CLS_MODEL",
        description="Path to RapidOCR classification model"
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
    
    # Reranker Configuration
    reranker_mode: str = Field(
        default="api",
        alias="OPENRECALL_RERANKER_MODE",
        description="Reranker mode: 'api' or 'local'"
    )
    reranker_url: str = Field(
        default="http://localhost:8080/rerank",
        alias="OPENRECALL_RERANKER_URL",
        description="URL for the reranker API (compatible with TEI/BGE)"
    )
    reranker_model: str = Field(
        default="Qwen/Qwen3-Reranker-0.6B",
        alias="OPENRECALL_RERANKER_MODEL",
        description="Model name/path for the reranker"
    )
    reranker_api_key: str = Field(
        default="",
        alias="OPENRECALL_RERANKER_API_KEY",
        description="Optional API key specifically for the reranker service"
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
    fusion_log_enabled: bool = Field(
        default=False,
        alias="OPENRECALL_FUSION_LOG_ENABLED",
        description="Whether to log fusion text to a file for debugging"
    )
    deployment_mode: str = Field(
        default="local",
        alias="OPENRECALL_DEPLOYMENT_MODE",
        description="Deployment mode: local, remote, debian_client, debian_server"
    )

    # Phase 1: Video Recording Configuration
    recording_mode: str = Field(
        default="auto",
        alias="OPENRECALL_RECORDING_MODE",
        description="Recording mode: video, screenshot, auto (auto tries video first, falls back to screenshot)"
    )
    video_chunk_duration: int = Field(
        default=60,
        alias="OPENRECALL_VIDEO_CHUNK_DURATION",
        description="Video chunk duration target in seconds (chunk_process uses strict monotonic wallclock)."
    )
    video_fps: int = Field(
        default=30,
        alias="OPENRECALL_VIDEO_FPS",
        description="Video recording FPS"
    )
    video_crf: int = Field(
        default=23,
        alias="OPENRECALL_VIDEO_CRF",
        description="Video encoding quality (lower=better quality, 0-51)"
    )
    video_monitor_ids: str = Field(
        default="",
        alias="OPENRECALL_VIDEO_MONITOR_IDS",
        description="Comma-separated monitor IDs for monitor-id capture. Empty means auto-select."
    )
    video_pipeline_restart_on_profile_change: bool = Field(
        default=True,
        alias="OPENRECALL_VIDEO_PIPELINE_RESTART_ON_PROFILE_CHANGE",
        description="Immediately restart per-monitor pipeline on input profile changes."
    )
    video_pool_max_bytes: int = Field(
        default=64 * 1024 * 1024,
        alias="OPENRECALL_VIDEO_POOL_MAX_BYTES",
        description="Maximum persistent frame buffer size per monitor (bytes)."
    )
    video_segment_stagger_seconds: int = Field(
        default=2,
        alias="OPENRECALL_VIDEO_SEGMENT_STAGGER_SECONDS",
        description="Delay applied between multi-monitor pipeline starts to reduce simultaneous segment IO bursts."
    )
    video_pipe_write_warn_ms: int = Field(
        default=50,
        alias="OPENRECALL_VIDEO_PIPE_WRITE_WARN_MS",
        description="Warn when a single ffmpeg stdin frame write exceeds this latency (ms)."
    )
    video_pipeline_mode: str = Field(
        default="chunk_process",
        alias="OPENRECALL_VIDEO_PIPELINE_MODE",
        description="Video pipeline mode: segment|chunk_process."
    )
    video_pipe_write_timeout_ms: int = Field(
        default=1500,
        alias="OPENRECALL_VIDEO_PIPE_WRITE_TIMEOUT_MS",
        description="Timeout for a single ffmpeg stdin write in milliseconds."
    )
    video_no_chunk_progress_timeout_seconds: int = Field(
        default=180,
        alias="OPENRECALL_VIDEO_NO_CHUNK_PROGRESS_TIMEOUT_SECONDS",
        description="Segment-mode only: restart pipeline when chunk boundary has no progress for this many seconds."
    )
    video_color_range: str = Field(
        default="auto",
        alias="OPENRECALL_VIDEO_COLOR_RANGE",
        description="Raw input color range policy: auto|tv|pc."
    )
    sck_start_retry_max: int = Field(
        default=3,
        alias="OPENRECALL_SCK_START_RETRY_MAX",
        description="How many short SCK startup retries are attempted before falling back to legacy capture."
    )
    sck_retry_backoff_seconds: int = Field(
        default=2,
        alias="OPENRECALL_SCK_RETRY_BACKOFF_SECONDS",
        description="Backoff between regular SCK startup retries (seconds)."
    )
    sck_permission_backoff_seconds: int = Field(
        default=30,
        alias="OPENRECALL_SCK_PERMISSION_BACKOFF_SECONDS",
        description="Backoff after SCK permission_denied before retrying (seconds)."
    )
    sck_recovery_probe_seconds: int = Field(
        default=5,
        alias="OPENRECALL_SCK_RECOVERY_PROBE_SECONDS",
        description="Probe interval to recover from legacy fallback back to monitor-id/SCK mode."
    )
    sck_auto_recover_from_legacy: bool = Field(
        default=True,
        alias="OPENRECALL_SCK_AUTO_RECOVER_FROM_LEGACY",
        description="Whether to automatically probe and recover from legacy fallback to SCK mode."
    )

    frame_extraction_interval: float = Field(
        default=5.0,
        alias="OPENRECALL_FRAME_EXTRACTION_INTERVAL",
        description="Seconds between extracted frames (default: 5.0 = 1 frame per 5s)"
    )
    frame_dedup_threshold: float = Field(
        default=0.95,
        alias="OPENRECALL_FRAME_DEDUP_THRESHOLD",
        description="MSSIM threshold for frame deduplication (0.0-1.0)"
    )
    retention_days: int = Field(
        default=30,
        alias="OPENRECALL_RETENTION_DAYS",
        description="Number of days to retain data before auto-deletion"
    )
    retention_check_interval: int = Field(
        default=21600,
        alias="OPENRECALL_RETENTION_CHECK_INTERVAL",
        description="Seconds between retention cleanup runs (default: 21600 = 6 hours)"
    )

    # Phase 2: Audio Recording Configuration
    audio_enabled: bool = Field(
        default=True,
        alias="OPENRECALL_AUDIO_ENABLED",
        description="Enable audio capture (system audio + microphone)"
    )
    audio_sample_rate: int = Field(
        default=16000,
        alias="OPENRECALL_AUDIO_SAMPLE_RATE",
        description="Audio sample rate in Hz (16000 for Whisper compatibility)"
    )
    audio_channels: int = Field(
        default=1,
        alias="OPENRECALL_AUDIO_CHANNELS",
        description="Audio channels (1=mono for Whisper)"
    )
    audio_chunk_duration: int = Field(
        default=60,
        alias="OPENRECALL_AUDIO_CHUNK_DURATION",
        description="Audio chunk duration in seconds"
    )
    audio_format: str = Field(
        default="wav",
        alias="OPENRECALL_AUDIO_FORMAT",
        description="Audio file format (wav)"
    )
    audio_device_system: str = Field(
        default="",
        alias="OPENRECALL_AUDIO_DEVICE_SYSTEM",
        description="System audio device name or index (requires virtual device like BlackHole on macOS)"
    )
    audio_device_mic: str = Field(
        default="",
        alias="OPENRECALL_AUDIO_DEVICE_MIC",
        description="Microphone device name or index (empty=default input)"
    )
    audio_vad_threshold: float = Field(
        default=0.5,
        alias="OPENRECALL_AUDIO_VAD_THRESHOLD",
        description="VAD speech probability threshold (0.0-1.0)"
    )
    audio_vad_min_speech_ratio: float = Field(
        default=0.05,
        alias="OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO",
        description="Minimum speech ratio in chunk required before transcription"
    )
    audio_vad_smoothing_window_frames: int = Field(
        default=10,
        alias="OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES",
        description="Rolling smoothing window size for frame-level VAD decisions"
    )
    audio_vad_hysteresis_on_frames: int = Field(
        default=3,
        alias="OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES",
        description="Consecutive speech-like frames needed to enter speech state"
    )
    audio_vad_hysteresis_off_frames: int = Field(
        default=5,
        alias="OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES",
        description="Consecutive silence-like frames needed to exit speech state"
    )
    audio_vad_backend: str = Field(
        default="silero",
        alias="OPENRECALL_AUDIO_VAD_BACKEND",
        description="VAD backend: silero (default) or webrtcvad"
    )
    audio_whisper_model: str = Field(
        default="base",
        alias="OPENRECALL_AUDIO_WHISPER_MODEL",
        description="Whisper model size: tiny, base, small, medium, large-v3"
    )
    audio_whisper_compute_type: str = Field(
        default="int8",
        alias="OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE",
        description="Whisper compute type: int8 (CPU), float16 (GPU), float32"
    )
    audio_whisper_language: str = Field(
        default="en",
        alias="OPENRECALL_AUDIO_WHISPER_LANGUAGE",
        description="Whisper transcription language code"
    )
    audio_whisper_beam_size: int = Field(
        default=5,
        alias="OPENRECALL_AUDIO_WHISPER_BEAM_SIZE",
        description="Whisper beam search size"
    )

    @field_validator(
        "server_data_dir", 
        "client_data_dir", 
        "cache_dir", 
        "client_screenshots_dir", 
        "base_path_legacy",
        mode="before"
    )
    @classmethod
    def expand_path(cls, v: Optional[Union[str, Path]]) -> Optional[Path]:
        if v is None:
            return None
        return Path(str(v)).expanduser().resolve()

    @field_validator("video_pipeline_mode")
    @classmethod
    def validate_video_pipeline_mode(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in {"segment", "chunk_process"}:
            raise ValueError("OPENRECALL_VIDEO_PIPELINE_MODE must be one of: segment, chunk_process")
        return normalized

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
        """Path to the SQLite database file."""
        return self.server_data_dir / "db" / "recall.db"

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
    def frames_path(self) -> Path:
        """Directory for storing extracted frame images (Server side)."""
        return self.server_data_dir / "frames"

    @property
    def video_chunks_path(self) -> Path:
        """Directory for storing video chunk files (Server side)."""
        return self.server_data_dir / "video_chunks"

    @property
    def client_video_chunks_path(self) -> Path:
        """Directory for client-side video chunk output."""
        return self.client_data_dir / "video_chunks"

    @property
    def client_audio_chunks_path(self) -> Path:
        """Directory for client-side audio chunk output."""
        return self.client_data_dir / "audio_chunks"

    @property
    def server_audio_path(self) -> Path:
        """Directory for storing audio chunk files (Server side)."""
        return self.server_data_dir / "audio"

    @property
    def video_monitor_id_list(self) -> list[str]:
        """Parsed list for OPENRECALL_VIDEO_MONITOR_IDS."""
        return [item.strip() for item in self.video_monitor_ids.split(",") if item.strip()]
    
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
            self.db_path.parent,
            self.lancedb_path,
            self.model_cache_path,
            self.cache_path,
            self.frames_path,
            self.video_chunks_path,
            self.client_video_chunks_path,
            self.client_audio_chunks_path,
            self.server_audio_path,
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
