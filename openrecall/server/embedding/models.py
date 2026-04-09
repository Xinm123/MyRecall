"""Embedding models for frame vector storage."""
from __future__ import annotations

from typing import Optional
from lancedb.pydantic import LanceModel, Vector
from pydantic import Field


class FrameEmbedding(LanceModel):
    """Frame embedding for LanceDB storage.

    Stores multimodal (image + text) embedding for a frame.
    """

    frame_id: int = Field(description="Reference to frames.id")
    embedding_vector: Vector(1024) = Field(
        description="Multimodal embedding vector (1024 dimensions)"
    )
    embedding_model: str = Field(
        default="qwen3-vl-embedding",
        description="Model used to generate embedding",
    )

    # Redundant metadata for filtering without JOIN
    timestamp: str = Field(description="Frame timestamp (ISO8601 UTC)")
    app_name: str = Field(default="", description="Application name")
    window_name: str = Field(default="", description="Window title")

    def to_storage_dict(self) -> dict:
        """Convert to dict for LanceDB storage."""
        return {
            "frame_id": self.frame_id,
            "embedding_vector": self.embedding_vector,
            "embedding_model": self.embedding_model,
            "timestamp": self.timestamp,
            "app_name": self.app_name,
            "window_name": self.window_name,
        }
