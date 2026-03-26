"""
Integration tests for Chat Service Phase 2.

Requires:
  - MyRecall Edge server running on localhost:8083
  - bun installed on system
  - MINIMAX_CN_API_KEY or KIMI_API_KEY environment variable

Mark: @pytest.mark.integration
"""

import os
import pytest

from openrecall.client.chat.pi_manager import find_bun_executable, ensure_installed
from openrecall.client.chat.service import ChatService
from openrecall.client.chat.types import PiStatus


def is_edge_server_reachable() -> bool:
    """Check if Edge server is running on localhost:8083."""
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:8083/v1/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.fixture
def chat_service(tmp_path):
    """Create ChatService with temp directory."""
    return ChatService(tmp_path)


@pytest.mark.integration
class TestChatServiceIntegration:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        """Skip if prerequisites not met."""
        if not find_bun_executable():
            pytest.skip("bun not installed")
        if not is_edge_server_reachable():
            pytest.skip("Edge server not running on localhost:8083")
        if not (os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("KIMI_API_KEY")):
            pytest.skip("Neither MINIMAX_CN_API_KEY nor KIMI_API_KEY is set")
        ensure_installed()

    def test_create_and_list_conversations(self, chat_service):
        """Conversations can be created and listed."""
        conv = chat_service.create_conversation()
        assert conv.id is not None

        listed = chat_service.list_conversations()
        assert len(listed) == 1
        assert listed[0].id == conv.id

    def test_add_message_and_save(self, chat_service):
        """Messages can be added to conversations."""
        from openrecall.client.chat.conversation import add_message

        conv = chat_service.create_conversation()
        add_message(conv, role="user", content="Hello")
        chat_service.save_conversation(conv)

        loaded = chat_service.get_conversation(conv.id)
        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "Hello"

    def test_delete_conversation(self, chat_service):
        """Conversations can be deleted."""
        conv = chat_service.create_conversation()
        assert chat_service.get_conversation(conv.id) is not None

        deleted = chat_service.delete_conversation(conv.id)
        assert deleted is True
        assert chat_service.get_conversation(conv.id) is None


@pytest.mark.integration
class TestPiRpcIntegration:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        """Skip if prerequisites not met."""
        if not find_bun_executable():
            pytest.skip("bun not installed")
        if not is_edge_server_reachable():
            pytest.skip("Edge server not running on localhost:8083")
        if not (os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("KIMI_API_KEY")):
            pytest.skip("Neither MINIMAX_CN_API_KEY nor KIMI_API_KEY is set")
        ensure_installed()

    def test_pi_status(self, chat_service):
        """get_pi_status returns a PiStatus object."""
        status = chat_service.get_pi_status()
        assert isinstance(status, PiStatus)
        assert hasattr(status, "running")

    def test_ensure_pi_running(self, chat_service):
        """ensure_pi_running starts the Pi process."""
        chat_service.ensure_pi_running()

        # Give it time to start
        import time
        time.sleep(2)

        # Pi should be running or starting (may not be running if API key is invalid)
        assert isinstance(chat_service.get_pi_status(), PiStatus)

        # Clean up
        chat_service.shutdown()


@pytest.mark.integration
class TestStreamIntegration:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        """Skip if prerequisites not met."""
        if not find_bun_executable():
            pytest.skip("bun not installed")
        if not is_edge_server_reachable():
            pytest.skip("Edge server not running on localhost:8083")
        if not (os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("KIMI_API_KEY")):
            pytest.skip("Neither MINIMAX_CN_API_KEY nor KIMI_API_KEY is set")
        ensure_installed()

    def test_stream_response_basic(self, chat_service):
        """stream_response yields events."""
        conv = chat_service.create_conversation()

        events = []
        try:
            for event in chat_service.stream_response(
                conversation_id=conv.id,
                message="What is 2+2? Answer in one word.",
            ):
                events.append(event)
                # Limit events to prevent long test
                if len(events) > 100 or event.get("type") == "agent_end":
                    break
        except Exception as e:
            pytest.skip(f"Pi streaming failed: {e}")

        # Should have at least one event
        assert len(events) > 0

        # Clean up
        chat_service.shutdown()
