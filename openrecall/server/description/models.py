"""Description models for frame description generation."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class FrameDescription(BaseModel):
    """Structured description of a frame's content and user intent."""

    narrative: str = Field(
        ...,
        max_length=512,
        description="Detailed natural language description of the screen content and user intent",
    )
    entities: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Key entities extracted from the frame (max 10 items)",
    )
    intent: str = Field(
        ...,
        description="User intent in natural language phrase (e.g., 'authenticating to GitHub')",
    )
    summary: str = Field(
        ...,
        max_length=200,
        description="One-sentence summary (max 200 chars / ~50 words)",
    )

    def to_db_dict(self) -> dict:
        """Convert to dict for database insertion."""
        import json
        return {
            "narrative": self.narrative,
            "entities_json": json.dumps(self.entities),
            "intent": self.intent,
            "summary": self.summary,
        }


class FrameContext(BaseModel):
    """Context metadata passed to description provider."""
    app_name: Optional[str] = None
    window_name: Optional[str] = None
    browser_url: Optional[str] = None
    timestamp: Optional[float] = None
