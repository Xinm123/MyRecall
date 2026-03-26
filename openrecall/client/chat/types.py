"""Data models for Chat Service."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ToolCall:
    """Represents a tool call made by the assistant."""
    id: str
    name: str
    args: dict
    status: str  # "running" | "done" | "error"
    result: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "args": self.args,
            "status": self.status,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolCall":
        return cls(
            id=d["id"],
            name=d["name"],
            args=d["args"],
            status=d["status"],
            result=d.get("result"),
        )


@dataclass
class Message:
    """Represents a single message in a conversation."""
    role: str  # "user" | "assistant"
    content: str
    tool_calls: Optional[list["ToolCall"]] = None
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        tool_calls = None
        if d.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in d["tool_calls"]]
        created_at = d.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = _utc_now()
        return cls(
            role=d["role"],
            content=d["content"],
            tool_calls=tool_calls,
            created_at=created_at,
        )


@dataclass
class Conversation:
    """Represents a chat conversation."""
    id: str
    title: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Conversation":
        messages = [Message.from_dict(m) for m in d.get("messages", [])]
        created_at = d.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = _utc_now()
        updated_at = d.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = _utc_now()
        return cls(
            id=d["id"],
            title=d["title"],
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class ConversationMeta:
    """Metadata for listing conversations without full message history."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
        }


@dataclass
class PiStatus:
    """Status of the Pi (Personal Intelligence) process."""
    running: bool
    pid: Optional[int] = None
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "pid": self.pid,
            "session_id": self.session_id,
        }
