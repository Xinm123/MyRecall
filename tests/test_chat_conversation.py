"""Tests for conversation manager."""
import json
import pytest
from pathlib import Path
from datetime import datetime

from openrecall.client.chat.conversation import (
    ensure_chats_dir,
    create_conversation,
    load_conversation,
    save_conversation,
    list_conversations,
    delete_conversation,
    add_message,
)
from openrecall.client.chat.types import Conversation, Message


class TestEnsureChatsDir:
    def test_creates_directory(self, tmp_path, monkeypatch):
        """ensure_chats_dir creates the chats directory."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")
        result = ensure_chats_dir()
        assert result.exists()
        assert result.name == "chats"


class TestConversationCRUD:
    def test_create_conversation(self, tmp_path, monkeypatch):
        """create_conversation creates a new conversation with UUID."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        conv = create_conversation()
        assert conv.id is not None
        assert len(conv.id) == 36  # UUID format
        assert conv.title == ""
        assert conv.messages == []
        assert conv.created_at is not None

    def test_save_and_load_conversation(self, tmp_path, monkeypatch):
        """save_conversation persists and load_conversation retrieves."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        conv = create_conversation()
        conv.title = "Test Conversation"
        save_conversation(conv)

        loaded = load_conversation(conv.id)
        assert loaded is not None
        assert loaded.id == conv.id
        assert loaded.title == "Test Conversation"

    def test_load_nonexistent_returns_none(self, tmp_path, monkeypatch):
        """load_conversation returns None for nonexistent ID."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        result = load_conversation("nonexistent-id")
        assert result is None

    def test_delete_conversation(self, tmp_path, monkeypatch):
        """delete_conversation removes the conversation file."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        conv = create_conversation()
        save_conversation(conv)
        assert load_conversation(conv.id) is not None

        deleted = delete_conversation(conv.id)
        assert deleted is True
        assert load_conversation(conv.id) is None

    def test_delete_nonexistent_returns_false(self, tmp_path, monkeypatch):
        """delete_conversation returns False for nonexistent ID."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        result = delete_conversation("nonexistent-id")
        assert result is False


class TestListConversations:
    def test_list_conversations_sorted_by_updated_at(self, tmp_path, monkeypatch):
        """list_conversations returns conversations sorted by updated_at DESC."""
        import openrecall.client.chat.conversation as conv_mod
        import time
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        conv1 = create_conversation()
        conv1.title = "First"
        save_conversation(conv1)

        time.sleep(0.01)  # Ensure different timestamps

        conv2 = create_conversation()
        conv2.title = "Second"
        save_conversation(conv2)

        time.sleep(0.01)

        conv3 = create_conversation()
        conv3.title = "Third"
        save_conversation(conv3)

        listed = list_conversations()
        assert len(listed) == 3
        # Most recent first
        assert listed[0].title == "Third"
        assert listed[1].title == "Second"
        assert listed[2].title == "First"

    def test_list_empty_returns_empty_list(self, tmp_path, monkeypatch):
        """list_conversations returns empty list when no conversations."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")
        ensure_chats_dir()

        result = list_conversations()
        assert result == []


class TestAddMessage:
    def test_add_message_appends_to_conversation(self, tmp_path, monkeypatch):
        """add_message appends a message and updates timestamp."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        conv = create_conversation()
        old_updated = conv.updated_at

        msg = add_message(conv, role="user", content="Hello")
        assert len(conv.messages) == 1
        assert conv.messages[0].role == "user"
        assert conv.messages[0].content == "Hello"
        assert conv.updated_at >= old_updated

    def test_add_message_auto_generates_title(self, tmp_path, monkeypatch):
        """add_message auto-generates title from first user message."""
        import openrecall.client.chat.conversation as conv_mod
        monkeypatch.setattr(conv_mod, "CHATS_DIR", tmp_path / "chats")

        conv = create_conversation()
        assert conv.title == ""

        add_message(conv, role="user", content="This is a very long first message that should be truncated")
        assert "This is a very long first message" in conv.title
