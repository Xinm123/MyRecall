"""
Conversation manager for Chat Service.

Handles CRUD operations for conversations stored as JSON files.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .types import Conversation, Message, ConversationMeta


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

# Storage path: OPENRECALL_CLIENT_DATA_DIR/chats/ or ~/MRC/chats/
_CLIENT_DATA_DIR = Path(os.environ.get("OPENRECALL_CLIENT_DATA_DIR", Path.home() / "MRC"))
CHATS_DIR = _CLIENT_DATA_DIR / "chats"


def ensure_chats_dir() -> Path:
    """Ensure chats directory exists, return path."""
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    return CHATS_DIR


def create_conversation() -> Conversation:
    """Create a new conversation with UUID and timestamps."""
    ensure_chats_dir()
    conv = Conversation(
        id=str(uuid.uuid4()),
        title="",
        messages=[],
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    save_conversation(conv)
    return conv


def load_conversation(conversation_id: str) -> Optional[Conversation]:
    """Load conversation from JSON file. Returns None if not found."""
    ensure_chats_dir()
    path = CHATS_DIR / f"{conversation_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return Conversation.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        return None


def save_conversation(conversation: Conversation) -> None:
    """Save conversation to JSON file with atomic write."""
    ensure_chats_dir()
    conversation.updated_at = _utc_now()

    path = CHATS_DIR / f"{conversation.id}.json"
    temp_path = CHATS_DIR / f".tmp_{conversation.id}.json"

    # Atomic write: temp file + rename
    temp_path.write_text(json.dumps(conversation.to_dict(), indent=2))
    temp_path.rename(path)


def list_conversations() -> list[ConversationMeta]:
    """List all conversations sorted by updated_at DESC."""
    ensure_chats_dir()
    metas = []
    for path in CHATS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            conv = Conversation.from_dict(data)
            metas.append(ConversationMeta(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=len(conv.messages),
            ))
        except (json.JSONDecodeError, KeyError):
            continue

    # Sort by updated_at DESC
    metas.sort(key=lambda m: m.updated_at, reverse=True)
    return metas


def delete_conversation(conversation_id: str) -> bool:
    """Delete conversation file. Returns True if deleted, False if not found."""
    ensure_chats_dir()
    path = CHATS_DIR / f"{conversation_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def add_message(
    conversation: Conversation,
    role: str,
    content: str,
    tool_calls: Optional[list] = None
) -> Message:
    """Add a message to the conversation and auto-generate title if needed."""
    msg = Message(
        role=role,
        content=content,
        tool_calls=tool_calls,
        created_at=_utc_now(),
    )
    conversation.messages.append(msg)
    conversation.updated_at = _utc_now()

    # Auto-generate title from first user message
    if not conversation.title and role == "user":
        conversation.title = content[:50] + ("..." if len(content) > 50 else "")

    return msg
