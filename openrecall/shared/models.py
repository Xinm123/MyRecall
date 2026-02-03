"""Data models for OpenRecall using Pydantic."""

from typing import Any

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
