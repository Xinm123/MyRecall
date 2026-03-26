"""
Chat API routes (Flask Blueprint).

Endpoints:
- POST /chat/api/stream — SSE streaming chat response
- GET /chat/api/conversations — List conversations
- POST /chat/api/conversations — Create conversation
- GET /chat/api/conversations/<id> — Get conversation
- DELETE /chat/api/conversations/<id> — Delete conversation
- POST /chat/api/new-session — Reset Pi session
- GET /chat/api/pi-status — Get Pi process status
"""

import json
import os
from flask import Blueprint, Response, request, jsonify, g
from pathlib import Path

from .service import ChatService

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


def get_chat_service() -> ChatService:
    """Get or create ChatService instance."""
    if "chat_service" not in g:
        data_dir = Path(os.environ.get("OPENRECALL_CLIENT_DATA_DIR", Path.home() / "MRC"))
        g.chat_service = ChatService(data_dir)
    return g.chat_service


@chat_bp.route("/api/stream", methods=["POST"])
def stream():
    """
    Stream chat response via SSE.

    Request:
        {
            "conversation_id": "uuid",
            "message": "user message",
            "images": ["base64..."]  // optional
        }

    Response: text/event-stream
        event: message_update
        data: {"type":"message_update",...}

        event: agent_end
        data: {"type":"agent_end"}
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    conversation_id = data.get("conversation_id")
    message = data.get("message")
    images = data.get("images")

    if not conversation_id:
        return jsonify({"error": "Missing conversation_id"}), 400
    if not message:
        return jsonify({"error": "Missing message"}), 400

    service = get_chat_service()

    def generate():
        """Generate SSE events with keepalive support.

        Keepalive is handled by yielding from service every 15 seconds
        if no real events are available.
        """
        try:
            for event in service.stream_response(conversation_id, message, images):
                event_type = event.get("type", "message")

                # Handle keepalive as SSE comment (not an event)
                if event_type == "keepalive":
                    yield ": keepalive\n\n"
                    continue

                yield f"event: {event_type}\n"
                yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            error_event = {"type": "error", "message": str(e), "code": "INTERNAL_ERROR"}
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_bp.route("/api/conversations", methods=["GET"])
def list_conversations():
    """List all conversations."""
    service = get_chat_service()
    conversations = service.list_conversations()
    return jsonify({
        "conversations": [c.to_dict() for c in conversations]
    })


@chat_bp.route("/api/conversations", methods=["POST"])
def create_conversation():
    """Create a new conversation."""
    service = get_chat_service()
    conv = service.create_conversation()
    return jsonify(conv.to_dict())


@chat_bp.route("/api/conversations/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id: str):
    """Get a conversation by ID."""
    service = get_chat_service()
    conv = service.get_conversation(conversation_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(conv.to_dict())


@chat_bp.route("/api/conversations/<conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    service = get_chat_service()
    deleted = service.delete_conversation(conversation_id)
    if not deleted:
        return jsonify({"error": "Conversation not found"}), 404
    return "", 204


@chat_bp.route("/api/new-session", methods=["POST"])
def new_session():
    """Reset Pi session (clear context)."""
    service = get_chat_service()
    service.switch_conversation("")
    return jsonify({"success": True})


@chat_bp.route("/api/pi-status", methods=["GET"])
def pi_status():
    """Get Pi process status."""
    service = get_chat_service()
    status = service.get_pi_status()
    return jsonify(status.to_dict())
