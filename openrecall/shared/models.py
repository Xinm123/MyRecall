"""Data models for OpenRecall using Pydantic."""

from typing import Any, Generic, List, TypeVar

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator


class RecallEntry(BaseModel):
    """Represents a database entry with guaranteed type safety.

    The embedding field is always a numpy array, automatically converted
    from bytes if necessary (e.g., when reading from SQLite BLOB).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int | None = None
    timestamp: int
    app: str
    title: str | None = None
    text: str | None = None  # OCR result (None when PENDING)
    description: str | None = None  # AI-generated semantic description (None when PENDING)
    embedding: Any | None = None  # Embedding vector (None when PENDING)
    status: str = "PENDING"  # Task status: PENDING, PROCESSING, COMPLETED, FAILED
    similarity_score: float | None = None  # Similarity score for search results (0.0 to 1.0)

    @field_validator("embedding", mode="before")
    @classmethod
    def deserialize_embedding(cls, v: Any) -> np.ndarray | None:
        """Convert bytes to numpy array if necessary."""
        if v is None:
            return None
        if isinstance(v, bytes):
            return np.frombuffer(v, dtype=np.float32)
        if isinstance(v, np.ndarray):
            return v
        raise ValueError(f"embedding must be bytes, np.ndarray or None, got {type(v)}")


# ---------------------------------------------------------------------------
# v3 Phase 0: Multi-modal entity models
# ---------------------------------------------------------------------------

class VideoChunk(BaseModel):
    """Video chunk metadata (populated in Phase 1)."""
    id: int | None = None
    file_path: str
    device_name: str = ""
    created_at: str = ""
    expires_at: str | None = None
    encrypted: int = 0
    checksum: str | None = None


class Frame(BaseModel):
    """Video frame metadata (populated in Phase 1)."""
    id: int | None = None
    video_chunk_id: int
    offset_index: int
    timestamp: float
    app_name: str = ""
    window_name: str = ""
    focused: bool = False
    browser_url: str = ""
    created_at: str = ""


class OcrText(BaseModel):
    """OCR text extracted from a frame (populated in Phase 1)."""
    frame_id: int
    text: str
    text_json: str | None = None
    ocr_engine: str = ""
    text_length: int | None = None
    created_at: str = ""


class AudioChunk(BaseModel):
    """Audio chunk metadata (populated in Phase 2)."""
    id: int | None = None
    file_path: str
    timestamp: float
    start_time: float | None = None
    end_time: float | None = None
    is_input: bool | None = None
    source_kind: str = "unknown"
    device_name: str = ""
    created_at: str = ""
    expires_at: str | None = None
    encrypted: int = 0
    checksum: str | None = None


class AudioTranscription(BaseModel):
    """Audio transcription (populated in Phase 2).

    speaker_id is nullable per ADR-0004 (speaker identification optional).
    """
    id: int | None = None
    audio_chunk_id: int
    offset_index: int
    timestamp: float
    transcription: str
    transcription_engine: str = ""
    speaker_id: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    text_length: int | None = None
    created_at: str = ""


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination wrapper for API v1 responses (ADR-0002)."""
    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool
