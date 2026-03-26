"""Tests for chat types (Conversation, Message, ToolCall, etc.)."""
from datetime import datetime

from openrecall.client.chat.types import (
    Conversation,
    ConversationMeta,
    Message,
    PiStatus,
    ToolCall,
)


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_to_dict_basic(self):
        tc = ToolCall(
            id="tc_001",
            name="search_recall",
            args={"query": "python web scraping"},
            status="running",
        )
        d = tc.to_dict()
        assert d["id"] == "tc_001"
        assert d["name"] == "search_recall"
        assert d["args"] == {"query": "python web scraping"}
        assert d["status"] == "running"
        assert d["result"] is None

    def test_to_dict_with_result(self):
        tc = ToolCall(
            id="tc_002",
            name="search_recall",
            args={"query": "test"},
            status="done",
            result="found 42 frames",
        )
        d = tc.to_dict()
        assert d["result"] == "found 42 frames"


class TestMessage:
    """Tests for Message dataclass."""

    def test_user_role(self):
        msg = Message(role="user", content="What did I do yesterday?")
        assert msg.role == "user"
        assert msg.content == "What did I do yesterday?"
        assert msg.tool_calls is None
        assert isinstance(msg.created_at, datetime)

    def test_assistant_with_tool_calls(self):
        tc = ToolCall(
            id="tc_001",
            name="search_recall",
            args={"query": "browser tabs"},
            status="done",
            result="found 3 frames",
        )
        msg = Message(
            role="assistant",
            content="Let me search for that.",
            tool_calls=[tc],
        )
        assert msg.role == "assistant"
        assert msg.content == "Let me search for that."
        assert (msg.tool_calls and len(msg.tool_calls) == 1) and msg.tool_calls[0].name == "search_recall"

    def test_to_dict_roundtrip(self):
        msg = Message(
            role="user",
            content="Show me screenshots from yesterday",
            created_at=datetime(2026, 3, 26, 10, 30, 0),
        )
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.role == msg.role
        assert restored.content == msg.content
        assert restored.tool_calls is None
        assert restored.created_at == msg.created_at

    def test_to_dict_with_tool_calls_roundtrip(self):
        tc = ToolCall(
            id="tc_xyz",
            name="get_screenshot",
            args={"frame_id": "f123"},
            status="done",
            result="image bytes",
        )
        msg = Message(
            role="assistant",
            content="Here is the screenshot.",
            tool_calls=[tc],
            created_at=datetime(2026, 3, 26, 11, 0, 0),
        )
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.role == msg.role
        assert restored.content == msg.content
        tcs = restored.tool_calls
        assert (tcs and len(tcs) == 1) and tcs[0].id == "tc_xyz"
        assert tcs[0].result == "image bytes"


class TestConversation:
    """Tests for Conversation dataclass."""

    def test_create_with_all_fields(self):
        created = datetime(2026, 3, 26, 9, 0, 0)
        updated = datetime(2026, 3, 26, 9, 15, 0)
        msg1 = Message(role="user", content="Hello", created_at=created)
        msg2 = Message(role="assistant", content="Hi there!", created_at=created)
        conv = Conversation(
            id="conv_abc123",
            title="Browser research",
            messages=[msg1, msg2],
            created_at=created,
            updated_at=updated,
        )
        assert conv.id == "conv_abc123"
        assert conv.title == "Browser research"
        assert len(conv.messages) == 2
        assert conv.messages[0].content == "Hello"
        assert conv.messages[1].content == "Hi there!"
        assert conv.created_at == created
        assert conv.updated_at == updated

    def test_to_dict_roundtrip(self):
        created = datetime(2026, 3, 26, 12, 0, 0)
        updated = datetime(2026, 3, 26, 12, 30, 0)
        msg = Message(
            role="assistant",
            content="Done!",
            created_at=created,
        )
        conv = Conversation(
            id="conv_roundtrip",
            title="Test roundtrip",
            messages=[msg],
            created_at=created,
            updated_at=updated,
        )
        d = conv.to_dict()
        restored = Conversation.from_dict(d)
        assert restored.id == conv.id
        assert restored.title == conv.title
        assert len(restored.messages) == 1
        assert restored.messages[0].content == "Done!"
        assert restored.created_at == conv.created_at
        assert restored.updated_at == conv.updated_at

    def test_empty_messages_default(self):
        conv = Conversation(id="conv_empty", title="Empty chat")
        assert conv.messages == []
        assert isinstance(conv.created_at, datetime)
        assert isinstance(conv.updated_at, datetime)


class TestConversationMeta:
    """Tests for ConversationMeta dataclass."""

    def test_all_fields(self):
        created = datetime(2026, 3, 26, 8, 0, 0)
        updated = datetime(2026, 3, 26, 10, 0, 0)
        meta = ConversationMeta(
            id="conv_meta_001",
            title="Search session",
            created_at=created,
            updated_at=updated,
            message_count=5,
        )
        assert meta.id == "conv_meta_001"
        assert meta.title == "Search session"
        assert meta.created_at == created
        assert meta.updated_at == updated
        assert meta.message_count == 5

    def test_to_dict(self):
        created = datetime(2026, 3, 26, 8, 0, 0)
        updated = datetime(2026, 3, 26, 10, 0, 0)
        meta = ConversationMeta(
            id="conv_meta_002",
            title="Another session",
            created_at=created,
            updated_at=updated,
            message_count=3,
        )
        d = meta.to_dict()
        assert d["id"] == "conv_meta_002"
        assert d["title"] == "Another session"
        assert d["created_at"] == created.isoformat()
        assert d["updated_at"] == updated.isoformat()
        assert d["message_count"] == 3


class TestPiStatus:
    """Tests for PiStatus dataclass."""

    def test_running_state(self):
        status = PiStatus(running=True, pid=12345, session_id="sess_abc")
        assert status.running is True
        assert status.pid == 12345
        assert status.session_id == "sess_abc"

    def test_stopped_state(self):
        status = PiStatus(running=False)
        assert status.running is False
        assert status.pid is None
        assert status.session_id is None

    def test_to_dict(self):
        status = PiStatus(running=True, pid=99999, session_id="sess_xyz")
        d = status.to_dict()
        assert d["running"] is True
        assert d["pid"] == 99999
        assert d["session_id"] == "sess_xyz"

    def test_to_dict_stopped(self):
        status = PiStatus(running=False)
        d = status.to_dict()
        assert d["running"] is False
        assert d["pid"] is None
        assert d["session_id"] is None
