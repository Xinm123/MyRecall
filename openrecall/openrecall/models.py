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
    text: str
    embedding: Any  # Will be np.ndarray after validation
    
    @field_validator("embedding", mode="before")
    @classmethod
    def deserialize_embedding(cls, v: Any) -> np.ndarray:
        """Convert bytes to numpy array if necessary."""
        if isinstance(v, bytes):
            return np.frombuffer(v, dtype=np.float32)
        if isinstance(v, np.ndarray):
            return v
        raise ValueError(f"embedding must be bytes or np.ndarray, got {type(v)}")
