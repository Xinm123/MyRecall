from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from lancedb.pydantic import LanceModel, Vector


class Context(BaseModel):
    """Contextual metadata for the snapshot."""
    app_name: str
    window_title: str
    timestamp: float
    time_bucket: str = Field(description="Time bucket for partitioning, e.g., '2024-01-24-10'")


class Content(BaseModel):
    """Content extracted from the snapshot."""
    ocr_text: str = Field(description="Full text extracted via OCR for FTS")
    ocr_head: str = Field(description="First 300 chars for embedding context")
    caption: str = Field(description="Natural language description of the scene")
    keywords: List[str] = Field(default_factory=list, description="Extracted entities and keywords")
    scene_tag: str = Field(default="", description="Scene classification, e.g., 'coding'")
    action_tag: str = Field(default="", description="Action classification, e.g., 'debugging'")


class SemanticSnapshot(LanceModel):
    """The main entity representing a semantic snapshot of the user's screen."""
    id: str = Field(description="UUID string")
    image_path: str
    context: Context
    content: Content
    # Use LanceDB Vector type for vector search optimization
    embedding_vector: Vector(1024) = Field(description="The fusion text embedding")
    embedding_model: str = Field(default="qwen-text-v1")
    embedding_dim: int = Field(default=1024)
    # Exclude score from database schema (used for UI runtime only)
    score: Optional[float] = Field(default=None, exclude=True)
