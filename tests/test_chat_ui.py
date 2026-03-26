"""Tests for Chat UI page rendering."""
import pytest


@pytest.fixture
def client():
    """Create test client."""
    from openrecall.client.web.app import client_app as app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestChatPage:
    def test_chat_page_renders(self, client):
        """GET /chat returns 200 and contains chat layout."""
        resp = client.get("/chat")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "chat-layout" in data
        assert "chat-sidebar" in data
        assert "chat-main" in data
        assert "conversation-list" in data

    def test_chat_page_has_input_area(self, client):
        """Chat page has a message input area."""
        resp = client.get("/chat")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert 'class="chat-input"' in data
        assert 'class="chat-send-btn"' in data

    def test_chat_page_has_alpine_app(self, client):
        """Chat page initializes Alpine.js chatApp."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "chatApp()" in data
        assert "x-data" in data
        assert "conversations" in data

    def test_chat_page_has_marked_js(self, client):
        """Chat page loads marked.js from CDN."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "marked" in data

    def test_chat_page_has_tool_call_styles(self, client):
        """Chat page includes tool call styling."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "tool-call" in data
        assert "tool-calls-container" in data

    def test_chat_page_has_error_card_styles(self, client):
        """Chat page includes error card styling."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "error-card" in data
