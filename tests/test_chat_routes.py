"""Tests for Chat API routes."""
import json
import pytest


@pytest.fixture
def client():
    """Create test client."""
    from openrecall.client.web.app import client_app as app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def chat_service(tmp_path):
    """Create ChatService with temp directory."""
    from openrecall.client.chat.service import ChatService
    return ChatService(tmp_path)


class TestConversationRoutes:
    def test_list_conversations(self, client):
        """GET /chat/api/conversations returns list."""
        resp = client.get("/chat/api/conversations")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "conversations" in data

    def test_create_conversation(self, client):
        """POST /chat/api/conversations creates a conversation."""
        resp = client.post("/chat/api/conversations")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "id" in data

    def test_get_conversation(self, client):
        """GET /chat/api/conversations/<id> returns conversation."""
        # First create one
        create_resp = client.post("/chat/api/conversations")
        conv_id = json.loads(create_resp.data)["id"]

        # Then get it
        resp = client.get(f"/chat/api/conversations/{conv_id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["id"] == conv_id

    def test_get_nonexistent_conversation(self, client):
        """GET /chat/api/conversations/<id> returns 404 for nonexistent."""
        resp = client.get("/chat/api/conversations/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_conversation(self, client):
        """DELETE /chat/api/conversations/<id> removes conversation."""
        # First create one
        create_resp = client.post("/chat/api/conversations")
        conv_id = json.loads(create_resp.data)["id"]

        # Then delete it
        resp = client.delete(f"/chat/api/conversations/{conv_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/chat/api/conversations/{conv_id}")
        assert get_resp.status_code == 404


class TestPiStatusRoute:
    def test_get_pi_status(self, client):
        """GET /chat/api/pi-status returns status."""
        resp = client.get("/chat/api/pi-status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "running" in data


class TestNewSessionRoute:
    def test_new_session(self, client):
        """POST /chat/api/new-session resets Pi session."""
        resp = client.post("/chat/api/new-session")
        assert resp.status_code == 200


class TestStreamRoute:
    def test_stream_missing_conversation_id(self, client):
        """POST /chat/api/stream returns 400 without conversation_id."""
        resp = client.post(
            "/chat/api/stream",
            json={"message": "Hello"},
        )
        assert resp.status_code == 400

    def test_stream_missing_message(self, client):
        """POST /chat/api/stream returns 400 without message."""
        resp = client.post(
            "/chat/api/stream",
            json={"conversation_id": "test-id"},
        )
        assert resp.status_code == 400
