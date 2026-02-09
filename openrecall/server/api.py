"""REST API Blueprint for OpenRecall server.

Provides HTTP endpoints for client-server communication:
- Health check endpoint
- Fast screenshot ingestion endpoint (async processing)
- Legacy compatibility bridge for video-chunk uploads
"""

import logging
import time
import json
from pathlib import Path

import numpy as np
from flask import Blueprint, jsonify, request
from PIL import Image

from openrecall.server.database import SQLStore
from openrecall.server.config_runtime import runtime_settings
from openrecall.shared.config import settings
from openrecall.server.search.engine import SearchEngine

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")
sql_store = SQLStore()
search_engine = SearchEngine()


def _build_vision_status() -> dict:
    capture_mode = runtime_settings.capture_mode or "unknown"
    last_error = (runtime_settings.sck_last_error_code or "").strip()
    selected = list(runtime_settings.selected_monitors or [])

    status = "ok"
    if last_error == "permission_denied":
        status = "permission_denied"
    elif last_error in {"no_displays", "display_not_found"}:
        status = "no_monitors"
    elif last_error:
        status = "error"
    elif capture_mode == "legacy":
        status = "degraded_legacy"

    if capture_mode == "paused" and status == "degraded_legacy":
        status = "ok"

    return {
        "status": status,
        "active_mode": capture_mode,
        "selected_monitors": selected,
        "last_sck_error_code": last_error,
        "last_sck_error_at": runtime_settings.sck_last_error_at,
        "sck_available": bool(runtime_settings.sck_available),
    }


@api_bp.route("/search", methods=["GET"])
def search_api():
    """Hybrid Search Endpoint.
    
    Query Params:
        q: Search query string
        limit: Max results (default 50)
        
    Returns:
        JSON list of SemanticSnapshot objects.
    """
    q = (request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
        
    if not q:
        return jsonify([]), 200
        
    try:
        results = search_engine.search(q, limit=limit)
        
        # Serialize results to JSON
        serialized = []
        for snap in results:
            item = snap.model_dump()
            # Flatten some fields for easier UI consumption if needed, 
            # or just return the nested structure. 
            # User asked for: caption, scene_tag, app_name, timestamp, image_path
            # These are in: content.caption, content.scene_tag, context.app_name...
            # I will return the full object + flattened convenience fields.
            
            flat = {
                "id": snap.id,
                "timestamp": snap.context.timestamp,
                "app_name": snap.context.app_name,
                "window_title": snap.context.window_title,
                "caption": snap.content.caption,
                "scene_tag": snap.content.scene_tag,
                "image_path": snap.image_path,
                "full_data": item
            }
            serialized.append(flat)
            
        return jsonify(serialized), 200
    except Exception as e:
        logger.exception("Search error")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint.
    
    Returns:
        JSON response with status "ok" and HTTP 200.
    """
    return jsonify({"status": "ok"}), 200


@api_bp.route("/memories/latest", methods=["GET"])
def memories_latest():
    since_str = (request.args.get("since") or "0").strip()
    try:
        since = float(since_str)
    except ValueError:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Query parameter 'since' must be a float",
                }
            ),
            400,
        )

    try:
        memories = sql_store.get_memories_since(since)
        return jsonify(memories), 200
    except Exception as e:
        logger.exception("Error fetching latest memories")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/memories/recent", methods=["GET"])
def memories_recent():
    limit_str = (request.args.get("limit") or "200").strip()
    try:
        limit = int(limit_str)
    except ValueError:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Query parameter 'limit' must be an integer",
                }
            ),
            400,
        )

    try:
        memories = sql_store.get_recent_memories(limit=limit)
        return jsonify(memories), 200
    except Exception as e:
        logger.exception("Error fetching recent memories")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/queue/status", methods=["GET"])
def queue_status():
    """Get current processing queue status (debug endpoint).
    
    Returns:
        JSON with queue statistics and processing mode.
    """
    try:
        import sqlite3
        
        pending = sql_store.get_pending_count()
        
        # Get count by status
        with sqlite3.connect(str(settings.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM entries GROUP BY status")
            status_counts = dict(cursor.fetchall())
            video_status_counts = sql_store.get_video_chunk_status_counts(conn)
        
        processing_mode = "LIFO" if pending > settings.processing_lifo_threshold else "FIFO"
        
        response = {
            "queue": {
                "pending": pending,
                "processing": status_counts.get("PROCESSING", 0),
                "completed": status_counts.get("COMPLETED", 0),
                "failed": status_counts.get("FAILED", 0),
            },
            "video_queue": {
                "pending": video_status_counts.get("PENDING", 0),
                "processing": video_status_counts.get("PROCESSING", 0),
                "completed": video_status_counts.get("COMPLETED", 0),
                "failed": video_status_counts.get("FAILED", 0),
            },
            "config": {
                "lifo_threshold": settings.processing_lifo_threshold,
                "current_mode": processing_mode,
            },
            "system": {
                "debug": settings.debug,
                "device": settings.device,
                "reranker_mode": settings.reranker_mode,
                "reranker_model": settings.reranker_model,
            }
        }
        
        return jsonify(response), 200
    except Exception as e:
        logger.exception("Error getting queue status")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/upload", methods=["POST"])
def upload():
    """Fast screenshot ingestion endpoint (Fire-and-Forget).
    
    Accepts multipart/form-data:
    - file: Image file (PNG)
    - metadata: JSON string with timestamp, app_name, window_title
    
    Returns:
        HTTP 202 Accepted with task ID.
    """
    start_time = time.perf_counter()
    
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
        
    metadata_str = request.form.get('metadata')
    if not metadata_str:
        return jsonify({"status": "error", "message": "No metadata provided"}), 400
    
    try:
        metadata = json.loads(metadata_str)

        # Legacy compatibility:
        # If a video chunk is posted to /api/upload, forward to the v1 handler
        # instead of treating it as a screenshot PNG.
        is_video = (
            (file.content_type and file.content_type.startswith("video/"))
            or (file.filename and file.filename.endswith(".mp4"))
            or metadata.get("type") == "video_chunk"
        )
        if is_video:
            if settings.debug:
                logger.debug("📥 Legacy /api/upload detected video payload; forwarding to v1 video handler")
            from openrecall.server.api_v1 import _handle_video_upload

            return _handle_video_upload(file, metadata, start_time)

        timestamp = int(metadata.get("timestamp", 0))
        active_app = str(metadata.get("app_name", "Unknown"))
        active_window = str(metadata.get("window_title", "Unknown"))
        
        if settings.debug:
            logger.debug(f"📥 Upload request: app={active_app}, timestamp={timestamp}")
        
        # Save image to disk (Streaming)
        image_filename = f"{timestamp}.png"
        image_path = settings.screenshots_path / image_filename
        file.save(str(image_path))
        
        # Fast ingestion: Insert PENDING entry (no processing)
        task_id = sql_store.insert_pending_entry(
            timestamp=timestamp,
            app=active_app,
            title=active_window,
            image_path=str(image_path),
        )
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        if task_id:
            # Get current queue status for debug info
            pending_count = sql_store.get_pending_count() if settings.debug else 0
            
            if settings.debug:
                logger.debug(f"✅ HTTP 202 Accepted | task_id={task_id} | {elapsed_ms:.1f}ms | queue={pending_count}")
            else:
                logger.debug(f"Ingestion complete: {elapsed_ms:.1f}ms (task_id={task_id})")
            
            response_data = {
                "status": "accepted",
                "task_id": task_id,
                "message": "Queued for processing",
                "elapsed_ms": round(elapsed_ms, 1)
            }
            
            # Add queue info in debug mode
            if settings.debug:
                response_data["debug"] = {
                    "queue_size": pending_count,
                    "processing_mode": "LIFO" if pending_count > settings.processing_lifo_threshold else "FIFO"
                }
            
            return jsonify(response_data), 202  # HTTP 202 Accepted
        else:
            logger.warning(f"⚠️  Duplicate timestamp rejected: {timestamp}")
            return jsonify({
                "status": "error",
                "message": "Failed to insert entry (possibly duplicate)"
            }), 409  # Conflict
            
    except Exception as e:
        logger.exception("Upload ingestion error")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/upload/status", methods=["GET"])
def upload_status():
    """Legacy upload status endpoint for resume support."""
    checksum_raw = request.args.get("checksum", "").strip()
    checksum = checksum_raw.split(":", 1)[1] if checksum_raw.startswith("sha256:") else checksum_raw
    if not checksum:
        return jsonify({"status": "error", "message": "checksum required"}), 400

    video_path = settings.video_chunks_path / f"{checksum}.mp4"
    partial_path = video_path.with_suffix(".mp4.partial")

    if video_path.exists():
        return jsonify({"status": "completed", "bytes_received": video_path.stat().st_size}), 200
    if partial_path.exists():
        return jsonify({"status": "partial", "bytes_received": partial_path.stat().st_size}), 200
    return jsonify({"status": "not_found", "bytes_received": 0}), 200


@api_bp.route("/config", methods=["GET"])
def get_config():
    """Get current runtime configuration.
    
    Returns:
        JSON with all runtime settings plus client_online status.
        client_online is True if heartbeat was within last 15 seconds.
    """
    with runtime_settings._lock:
        config = runtime_settings.to_dict()
        client_online = (time.time() - runtime_settings.last_heartbeat) < 15
        config["client_online"] = client_online
    
    return jsonify(config), 200


@api_bp.route("/vision/status", methods=["GET"])
def vision_status():
    """Read-only capture health endpoint."""
    with runtime_settings._lock:
        return jsonify(_build_vision_status()), 200


@api_bp.route("/config", methods=["POST"])
def update_config():
    """Update runtime configuration.
    
    Accepts JSON payload with any subset of runtime settings:
    {
        "recording_enabled": bool,
        "upload_enabled": bool,
        "ai_processing_enabled": bool,
        "ui_show_ai": bool
    }
    
    Returns:
        JSON with updated configuration.
    """
    data = request.get_json()
    
    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
    
    valid_fields = {
        "recording_enabled",
        "upload_enabled",
        "ai_processing_enabled",
        "ui_show_ai"
    }
    
    try:
        with runtime_settings._lock:
            for field, value in data.items():
                if field not in valid_fields:
                    return jsonify({
                        "status": "error",
                        "message": f"Unknown field: {field}"
                    }), 400
                
                if not isinstance(value, bool):
                    return jsonify({
                        "status": "error",
                        "message": f"Field {field} must be boolean"
                    }), 400
                
                # Special handling for ai_processing_enabled:
                if field == "ai_processing_enabled" and not value and getattr(runtime_settings, field):
                    logger.info("AI processing disabled: Will stop picking up new tasks")
                    sql_store.cancel_processing_tasks()
                    runtime_settings.ai_processing_version += 1
                if field == "ai_processing_enabled" and value and not getattr(runtime_settings, field):
                    runtime_settings.ai_processing_version += 1

                setattr(runtime_settings, field, value)
                runtime_settings.notify_change()
            
            # Return updated config
            config = runtime_settings.to_dict()
            client_online = (time.time() - runtime_settings.last_heartbeat) < 15
            config["client_online"] = client_online
        
        return jsonify(config), 200
    
    except Exception as e:
        logger.exception("Error updating config")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Register client heartbeat.
    
    Updates the last_heartbeat timestamp and returns current config.
    Called by client to signal it's alive and online.
    
    Returns:
        JSON with status "ok" and current configuration.
    """
    try:
        with runtime_settings._lock:
            runtime_settings.last_heartbeat = time.time()
            payload = request.get_json(silent=True) or {}
            if isinstance(payload, dict):
                capture_mode = payload.get("capture_mode")
                if isinstance(capture_mode, str) and capture_mode.strip():
                    runtime_settings.capture_mode = capture_mode.strip()

                sck_available = payload.get("sck_available")
                if isinstance(sck_available, bool):
                    runtime_settings.sck_available = sck_available

                sck_last_error = payload.get("sck_last_error_code")
                if not isinstance(sck_last_error, str):
                    sck_last_error = payload.get("last_sck_error_code")
                if isinstance(sck_last_error, str):
                    runtime_settings.sck_last_error_code = sck_last_error.strip()

                sck_last_error_at = payload.get("sck_last_error_at")
                if sck_last_error_at is not None:
                    try:
                        runtime_settings.sck_last_error_at = float(sck_last_error_at)
                    except (TypeError, ValueError):
                        pass

                selected_monitors = payload.get("selected_monitors")
                if isinstance(selected_monitors, list):
                    runtime_settings.selected_monitors = [
                        str(m).strip() for m in selected_monitors if str(m).strip()
                    ]
                elif isinstance(selected_monitors, str):
                    runtime_settings.selected_monitors = [
                        item.strip() for item in selected_monitors.split(",") if item.strip()
                    ]

            config = runtime_settings.to_dict()
            client_online = (time.time() - runtime_settings.last_heartbeat) < 15
            config["client_online"] = client_online
        
        return jsonify({"status": "ok", "config": config}), 200
    
    except Exception as e:
        logger.exception("Error processing heartbeat")
        return jsonify({"status": "error", "message": str(e)}), 500
