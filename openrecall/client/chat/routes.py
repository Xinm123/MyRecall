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
- GET /chat/api/config — Get LLM config
- POST /chat/api/config — Save API key
"""

import json
import os
from flask import Blueprint, Response, request, jsonify
from pathlib import Path
from typing import Optional

from .service import ChatService
from .config_manager import get_current_config, save_api_key, save_user_choice, SUPPORTED_PROVIDERS

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")

# Module-level singleton (persists across requests)
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Get or create ChatService instance (process-level singleton)."""
    global _chat_service
    if _chat_service is None:
        data_dir = Path(os.environ.get("OPENRECALL_CLIENT_DATA_DIR", Path.home() / "MRC"))
        _chat_service = ChatService(data_dir)
    return _chat_service


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


@chat_bp.route("/api/pi-restart", methods=["POST"])
def pi_restart():
    """Restart Pi process (reloads extension)."""
    service = get_chat_service()
    if service._pi_manager:
        service._pi_manager.stop()
        service._pi_manager = None
    return jsonify({"success": True})


@chat_bp.route("/api/config", methods=["GET"])
def get_config():
    """
    Get current LLM configuration.

    Returns:
        {
            "provider": "qianfan",
            "model": "glm-5",
            "has_api_key": true,
            "supported_providers": [...]
        }
    """
    config = get_current_config()
    return jsonify(config)


@chat_bp.route("/api/config", methods=["POST"])
def save_config():
    """
    Save API key and model for a provider.

    Request:
        {
            "provider": "qianfan",
            "api_key": "your-api-key",
            "model": "glm-5",  // optional
            "api_base": "http://..."  // for custom provider
        }

    Returns:
        {"success": true}
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    provider = data.get("provider")
    api_key = data.get("api_key")
    model = data.get("model")
    api_base = data.get("api_base")

    if not provider:
        return jsonify({"error": "Missing provider"}), 400

    # Validate provider
    valid_providers = [p["id"] for p in SUPPORTED_PROVIDERS]
    if provider not in valid_providers:
        return jsonify({"error": f"Invalid provider. Must be one of: {', '.join(valid_providers)}"}), 400

    try:
        if api_key:
            save_api_key(provider, api_key, api_base)
        elif api_base and provider == "custom":
            # Save api_base even without new api_key (updates existing)
            save_api_key(provider, "", api_base)
        if model:
            save_user_choice(provider, model)

        # Restart Pi if running to apply new settings
        service = get_chat_service()
        if service._pi_manager and service._pi_manager.is_running():
            service._pi_manager.stop()
            service._pi_manager = None

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
