"""Description models for frame description generation."""
from __future__ import annotations

import json
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class FrameDescription(BaseModel):
    """Structured description of a frame's content and user intent."""

    narrative: str = Field(
        ...,
        max_length=2048,
        description="Detailed natural language description of screen content and user activity",
    )
    summary: str = Field(
        ...,
        max_length=256,
        description="One-sentence summary capturing the key activity",
    )
    tags: List[str] = Field(
        default_factory=list,
        min_length=0,
        max_length=10,
        description="3-8 lowercase keywords describing the activity (max 10 items)",
    )

    @field_validator("tags")
    @classmethod
    def tags_lowercase(cls, v: List[str]) -> List[str]:
        return [tag.lower().strip() for tag in v if tag.strip()]

    def to_db_dict(self) -> dict:
        """Convert to dict for database insertion."""
        return {
            "narrative": self.narrative,
            "summary": self.summary,
            "tags_json": json.dumps(self.tags),
        }


class FrameContext(BaseModel):
    """Context metadata passed to description provider."""
    app_name: Optional[str] = None
    window_name: Optional[str] = None
    browser_url: Optional[str] = None
