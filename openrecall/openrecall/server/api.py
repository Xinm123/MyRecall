"""REST API Blueprint for OpenRecall server.

Provides HTTP endpoints for client-server communication:
- Health check endpoint
- Fast screenshot ingestion endpoint (async processing)
"""

import logging
import time
import json
from pathlib import Path

import numpy as np
from flask import Blueprint, jsonify, request
from PIL import Image

from openrecall.server.database import (
    cancel_processing_tasks,
    get_memories_since,
    get_recent_memories,
    get_pending_count,
    insert_pending_entry,
    reset_stuck_tasks,
)
from openrecall.server.config_runtime import runtime_settings
from openrecall.shared.config import settings
from openrecall.server.search.engine import SearchEngine

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")
search_engine = SearchEngine()


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
        memories = get_memories_since(since)
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
        memories = get_recent_memories(limit=limit)
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
        from openrecall.server.database import get_pending_count
        import sqlite3
        
        pending = get_pending_count()
        
        # Get count by status
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
            "system": {
                "debug": settings.debug,
                "device": settings.device,
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
        task_id = insert_pending_entry(
            timestamp=timestamp,
            app=active_app,
            title=active_window,
            image_path=str(image_path),
        )
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        if task_id:
            # Get current queue status for debug info
            pending_count = get_pending_count() if settings.debug else 0
            
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
                    cancel_processing_tasks()
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
            config = runtime_settings.to_dict()
            client_online = (time.time() - runtime_settings.last_heartbeat) < 15
            config["client_online"] = client_online
        
        return jsonify({"status": "ok", "config": config}), 200
    
    except Exception as e:
        logger.exception("Error processing heartbeat")
        return jsonify({"status": "error", "message": str(e)}), 500
