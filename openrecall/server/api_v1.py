"""API v1 Blueprint for MyRecall server.

Provides versioned HTTP endpoints at /api/v1/* with:
- Pagination on list endpoints (ADR-0002)
- Auth placeholder on all routes
- Response envelope: { "data": [...], "meta": { "total", "limit", "offset", "has_more" } }

Legacy /api/* routes remain unchanged for backward compatibility.
"""

import logging
import time
import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from openrecall.server.auth import require_auth
from openrecall.server.database import SQLStore
from openrecall.server.config_runtime import runtime_settings
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
sql_store = SQLStore()

# Lazy import search engine to avoid circular imports
_search_engine = None


def _get_search_engine():
    global _search_engine
    if _search_engine is None:
        from openrecall.server.search.engine import SearchEngine
        _search_engine = SearchEngine()
    return _search_engine


def _paginate_response(items: list, total: int, limit: int, offset: int) -> dict:
    """Build a paginated response envelope."""
    return {
        "data": items,
        "meta": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        },
    }


def _parse_pagination(default_limit: int = 50, max_limit: int = 1000) -> tuple:
    """Parse limit/offset from query parameters.

    Returns:
        (limit, offset) tuple with validated values.
    """
    try:
        limit = int(request.args.get("limit", default_limit))
    except (ValueError, TypeError):
        limit = default_limit
    try:
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


@api_v1_bp.route("/health", methods=["GET"])
@require_auth
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


@api_v1_bp.route("/upload", methods=["POST"])
@require_auth
def upload():
    """Fast screenshot ingestion endpoint (mirrors /api/upload)."""
    start_time = time.perf_counter()

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No selected file"}), 400

    metadata_str = request.form.get("metadata")
    if not metadata_str:
        return jsonify({"status": "error", "message": "No metadata provided"}), 400

    try:
        metadata = json.loads(metadata_str)
        timestamp = int(metadata.get("timestamp", 0))
        active_app = str(metadata.get("app_name", "Unknown"))
        active_window = str(metadata.get("window_title", "Unknown"))

        image_filename = f"{timestamp}.png"
        image_path = settings.screenshots_path / image_filename
        file.save(str(image_path))

        task_id = sql_store.insert_pending_entry(
            timestamp=timestamp,
            app=active_app,
            title=active_window,
            image_path=str(image_path),
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if task_id:
            return jsonify({
                "status": "accepted",
                "task_id": task_id,
                "message": "Queued for processing",
                "elapsed_ms": round(elapsed_ms, 1),
            }), 202
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to insert entry (possibly duplicate)",
            }), 409

    except Exception as e:
        logger.exception("Upload ingestion error")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/search", methods=["GET"])
@require_auth
def search_api():
    """Hybrid search with pagination."""
    q = (request.args.get("q") or "").strip()
    limit, offset = _parse_pagination()

    if not q:
        return jsonify(_paginate_response([], 0, limit, offset)), 200

    try:
        search_engine = _get_search_engine()
        results = search_engine.search(q, limit=limit + offset)

        serialized = []
        for snap in results:
            flat = {
                "id": snap.id,
                "timestamp": snap.context.timestamp,
                "app_name": snap.context.app_name,
                "window_title": snap.context.window_title,
                "caption": snap.content.caption,
                "scene_tag": snap.content.scene_tag,
                "image_path": snap.image_path,
            }
            serialized.append(flat)

        total = len(serialized)
        page = serialized[offset: offset + limit]

        return jsonify(_paginate_response(page, total, limit, offset)), 200
    except Exception as e:
        logger.exception("Search error")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/memories/recent", methods=["GET"])
@require_auth
def memories_recent():
    """Get recent memories with pagination."""
    limit, offset = _parse_pagination(default_limit=200)

    try:
        # Fetch more than needed to support offset
        all_memories = sql_store.get_recent_memories(limit=limit + offset)
        total = len(all_memories)
        page = all_memories[offset: offset + limit]

        return jsonify(_paginate_response(page, total, limit, offset)), 200
    except Exception as e:
        logger.exception("Error fetching recent memories")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/memories/latest", methods=["GET"])
@require_auth
def memories_latest():
    """Get latest memories since timestamp, with pagination."""
    since_str = (request.args.get("since") or "0").strip()
    limit, offset = _parse_pagination()

    try:
        since = float(since_str)
    except ValueError:
        return jsonify({
            "status": "error",
            "message": "Query parameter 'since' must be a float",
        }), 400

    try:
        all_memories = sql_store.get_memories_since(since)
        total = len(all_memories)
        page = all_memories[offset: offset + limit]

        return jsonify(_paginate_response(page, total, limit, offset)), 200
    except Exception as e:
        logger.exception("Error fetching latest memories")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/queue/status", methods=["GET"])
@require_auth
def queue_status():
    """Get current processing queue status."""
    try:
        import sqlite3

        pending = sql_store.get_pending_count()

        with sqlite3.connect(str(settings.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM entries GROUP BY status")
            status_counts = dict(cursor.fetchall())

        processing_mode = "LIFO" if pending > settings.processing_lifo_threshold else "FIFO"

        response = {
            "queue": {
                "pending": pending,
                "processing": status_counts.get("PROCESSING", 0),
                "completed": status_counts.get("COMPLETED", 0),
                "failed": status_counts.get("FAILED", 0),
            },
            "config": {
                "lifo_threshold": settings.processing_lifo_threshold,
                "current_mode": processing_mode,
            },
        }

        return jsonify(response), 200
    except Exception as e:
        logger.exception("Error getting queue status")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/config", methods=["GET"])
@require_auth
def get_config():
    """Get current runtime configuration."""
    with runtime_settings._lock:
        config = runtime_settings.to_dict()
        client_online = (time.time() - runtime_settings.last_heartbeat) < 15
        config["client_online"] = client_online

    return jsonify(config), 200


@api_v1_bp.route("/config", methods=["POST"])
@require_auth
def update_config():
    """Update runtime configuration."""
    data = request.get_json()

    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    valid_fields = {
        "recording_enabled",
        "upload_enabled",
        "ai_processing_enabled",
        "ui_show_ai",
    }

    try:
        with runtime_settings._lock:
            for field, value in data.items():
                if field not in valid_fields:
                    return jsonify({
                        "status": "error",
                        "message": f"Unknown field: {field}",
                    }), 400

                if not isinstance(value, bool):
                    return jsonify({
                        "status": "error",
                        "message": f"Field {field} must be boolean",
                    }), 400

                if field == "ai_processing_enabled" and not value and getattr(runtime_settings, field):
                    sql_store.cancel_processing_tasks()
                    runtime_settings.ai_processing_version += 1
                if field == "ai_processing_enabled" and value and not getattr(runtime_settings, field):
                    runtime_settings.ai_processing_version += 1

                setattr(runtime_settings, field, value)
                runtime_settings.notify_change()

            config = runtime_settings.to_dict()
            client_online = (time.time() - runtime_settings.last_heartbeat) < 15
            config["client_online"] = client_online

        return jsonify(config), 200

    except Exception as e:
        logger.exception("Error updating config")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/heartbeat", methods=["POST"])
@require_auth
def heartbeat():
    """Register client heartbeat."""
    try:
        with runtime_settings._lock:
            runtime_settings.last_heartbeat = time.time()
            config = runtime_settings.to_dict()
            client_online = (time.time() - runtime_settings.last_heartbeat) < 15
            config["client_online"] = client_online

        return jsonify({"status": "ok", "config": config}), 200

    except Exception as e:
        logger.exception("Error processing heartbeat")
        return jsonify({"status": "error", "message": str(e)}), 500
