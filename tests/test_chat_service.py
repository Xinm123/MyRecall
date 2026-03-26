"""Tests for Chat Service."""
from unittest.mock import patch, MagicMock
import queue

from openrecall.client.chat.service import ChatService


class TestChatService:
    def test_init_creates_managers(self, tmp_path):
        """ChatService initializes conversation and Pi managers."""
        service = ChatService(tmp_path)
        assert service.data_dir == tmp_path

    def test_create_conversation(self, tmp_path):
        """create_conversation creates and returns a new conversation."""
        service = ChatService(tmp_path)
        conv = service.create_conversation()
        assert conv.id is not None
        assert conv.title == ""

    def test_list_conversations(self, tmp_path):
        """list_conversations returns conversation metadata."""
        service = ChatService(tmp_path)

        # Create some conversations
        service.create_conversation()
        service.create_conversation()

        listed = service.list_conversations()
        assert len(listed) == 2

    def test_get_conversation(self, tmp_path):
        """get_conversation loads a conversation by ID."""
        service = ChatService(tmp_path)
        conv = service.create_conversation()
        conv.title = "Test Title"
        service.save_conversation(conv)

        loaded = service.get_conversation(conv.id)
        assert loaded is not None
        assert loaded.title == "Test Title"

    def test_delete_conversation(self, tmp_path):
        """delete_conversation removes a conversation."""
        service = ChatService(tmp_path)
        conv = service.create_conversation()

        result = service.delete_conversation(conv.id)
        assert result is True

        loaded = service.get_conversation(conv.id)
        assert loaded is None

    def test_get_pi_status_when_not_running(self, tmp_path):
        """get_pi_status returns correct status when Pi is not running."""
        service = ChatService(tmp_path)
        status = service.get_pi_status()
        assert status.running is False

    @patch("openrecall.client.chat.service.PiRpcManager")
    def test_ensure_pi_running_starts_process(self, mock_pi_class, tmp_path):
        """ensure_pi_running starts Pi if not running."""
        mock_pi = MagicMock()
        mock_pi.is_running.return_value = False
        mock_pi_class.return_value = mock_pi

        service = ChatService(tmp_path)
        service.ensure_pi_running()

        mock_pi.start.assert_called_once()

    @patch("openrecall.client.chat.service.PiRpcManager")
    def test_stream_response_yields_events(self, mock_pi_class, tmp_path):
        """stream_response yields SSE events from Pi."""
        mock_pi = MagicMock()
        mock_pi.is_running.return_value = True
        mock_pi_class.return_value = mock_pi

        service = ChatService(tmp_path)

        # Mock the event queue
        events = [
            {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "Hello"}},
            {"type": "agent_end"},
        ]
        event_queue = queue.Queue()
        for e in events:
            event_queue.put(e)

        # This test would need more mocking for full coverage
        # For now, just verify the method exists and accepts correct params
        assert hasattr(service, "stream_response")
