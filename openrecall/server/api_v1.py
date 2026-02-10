"""API v1 Blueprint for MyRecall server.

Provides versioned HTTP endpoints at /api/v1/* with:
- Pagination on list endpoints (ADR-0002)
- Auth placeholder on all routes
- Response envelope: { "data": [...], "meta": { "total", "limit", "offset", "has_more" } }

Legacy /api/* routes remain unchanged for backward compatibility.
"""

import hashlib
import logging
import time
import json
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from openrecall.server.auth import require_auth
from openrecall.server.database import SQLStore
from openrecall.server.config_runtime import runtime_settings
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
sql_store = SQLStore()

# Lazy import search engine to avoid circular imports
_search_engine = None


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


def _extract_app_window(metadata: dict) -> tuple[str, str]:
    """Extract app/window metadata with backward-compatible key aliases."""
    app = str(
        metadata.get("app_name")
        or metadata.get("active_app")
        or "Unknown"
    )
    window = str(
        metadata.get("window_title")
        or metadata.get("active_window")
        or "Unknown"
    )
    return app, window


def _parse_pagination(default_limit: int = 50, max_limit: int = 1000) -> tuple:
    """Parse pagination query params with v1-compatible aliases.

    Supports both:
    - limit/offset (legacy)
    - page/page_size (remote-friendly)

    If both styles are provided, limit/offset takes precedence.
    Returns:
        (limit, offset) tuple with validated values.
    """
    # limit/offset keep priority for backward compatibility.
    limit_raw = request.args.get("limit")
    page_size_raw = request.args.get("page_size")
    offset_raw = request.args.get("offset")
    page_raw = request.args.get("page")

    try:
        if limit_raw is not None:
            limit = int(limit_raw)
        elif page_size_raw is not None:
            limit = int(page_size_raw)
        else:
            limit = default_limit
    except (ValueError, TypeError):
        limit = default_limit

    limit = max(1, min(limit, max_limit))

    try:
        if offset_raw is not None:
            offset = int(offset_raw)
        elif page_raw is not None:
            page = int(page_raw)
            if page < 1:
                page = 1
            offset = (page - 1) * limit
        else:
            offset = 0
    except (ValueError, TypeError):
        offset = 0

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
    """Fast ingestion endpoint for screenshots and video chunks."""
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

        # Detect video upload
        is_video = (
            (file.content_type and file.content_type.startswith("video/"))
            or (file.filename and file.filename.endswith(".mp4"))
            or metadata.get("type") == "video_chunk"
        )

        # Detect audio upload
        is_audio = (
            (file.content_type and file.content_type.startswith("audio/"))
            or (file.filename and file.filename.endswith(".wav"))
            or metadata.get("type") == "audio_chunk"
        )

        if is_video:
            return _handle_video_upload(file, metadata, start_time)
        elif is_audio:
            return _handle_audio_upload(file, metadata, start_time)
        else:
            return _handle_screenshot_upload(file, metadata, start_time)

    except Exception as e:
        logger.exception("Upload ingestion error")
        return jsonify({"status": "error", "message": str(e)}), 500


def _handle_screenshot_upload(file, metadata, start_time):
    """Handle screenshot upload (existing logic)."""
    timestamp = int(metadata.get("timestamp", 0))
    active_app, active_window = _extract_app_window(metadata)

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


def _handle_video_upload(file, metadata, start_time):
    """Handle video chunk upload."""
    checksum_raw = str(metadata.get("checksum", "") or "")
    checksum = checksum_raw.split(":", 1)[1] if checksum_raw.startswith("sha256:") else checksum_raw
    device_name = metadata.get("device_name", "")
    monitor_id = str(metadata.get("monitor_id", "") or "")
    monitor_width = int(metadata.get("monitor_width", 0) or 0)
    monitor_height = int(metadata.get("monitor_height", 0) or 0)
    monitor_is_primary = int(metadata.get("monitor_is_primary", 0) or 0)
    monitor_backend = str(metadata.get("monitor_backend", "") or "")
    monitor_fingerprint = str(metadata.get("monitor_fingerprint", "") or "")
    active_app, active_window = _extract_app_window(metadata)

    # Save to video_chunks_path
    settings.video_chunks_path.mkdir(parents=True, exist_ok=True)
    filename = f"{checksum}.mp4" if checksum else file.filename
    video_path = settings.video_chunks_path / filename

    # Support upload resume via X-Upload-Offset header
    upload_offset = request.headers.get("X-Upload-Offset")
    if upload_offset is not None:
        offset = int(upload_offset)
        partial_path = video_path.with_suffix(".mp4.partial")
        with open(partial_path, "ab") as f:
            f.seek(offset)
            f.write(file.read())
        total_size = metadata.get("file_size_bytes", 0)
        if total_size and partial_path.stat().st_size >= total_size:
            partial_path.rename(video_path)
        else:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return jsonify({
                "status": "partial",
                "bytes_received": partial_path.stat().st_size,
                "elapsed_ms": round(elapsed_ms, 1),
            }), 202
    else:
        file.save(str(video_path))

    # Verify checksum if provided
    if checksum:
        h = hashlib.sha256()
        with open(video_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        actual_checksum = h.hexdigest()
        if actual_checksum != checksum:
            logger.warning(f"Checksum mismatch: expected {checksum}, got {actual_checksum}")

    # Extract chunk time boundaries (Phase 1.5: for offset guard validation)
    chunk_start_time = metadata.get("start_time")
    if chunk_start_time is not None:
        chunk_start_time = float(chunk_start_time)
    chunk_end_time = metadata.get("end_time")
    if chunk_end_time is not None:
        chunk_end_time = float(chunk_end_time)

    # Insert into database
    chunk_id = sql_store.insert_video_chunk(
        file_path=str(video_path),
        device_name=device_name,
        checksum=checksum,
        app_name=active_app,
        window_name=active_window,
        monitor_id=monitor_id,
        monitor_width=monitor_width,
        monitor_height=monitor_height,
        monitor_is_primary=monitor_is_primary,
        monitor_backend=monitor_backend,
        monitor_fingerprint=monitor_fingerprint,
        start_time=chunk_start_time,
        end_time=chunk_end_time,
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if chunk_id:
        return jsonify({
            "status": "accepted",
            "chunk_id": chunk_id,
            "message": "Video chunk queued for processing",
            "elapsed_ms": round(elapsed_ms, 1),
        }), 202
    else:
        logger.error(
            "Video upload DB insert failed | path=%s | checksum=%s | monitor_id=%s",
            settings.db_path,
            checksum or "<none>",
            monitor_id or "<none>",
        )
        return jsonify({
            "status": "error",
            "message": "Failed to insert video chunk",
        }), 500


def _handle_audio_upload(file, metadata, start_time):
    """Handle audio chunk upload."""
    checksum_raw = str(metadata.get("checksum", "") or "")
    checksum = checksum_raw.split(":", 1)[1] if checksum_raw.startswith("sha256:") else checksum_raw
    device_name = metadata.get("device_name", "")
    timestamp = float(metadata.get("timestamp", 0))

    # Save to server_audio_path
    settings.server_audio_path.mkdir(parents=True, exist_ok=True)
    filename = f"{checksum}.wav" if checksum else file.filename
    audio_path = settings.server_audio_path / filename

    # Validate path stays within audio directory (prevent path traversal)
    if not audio_path.resolve().is_relative_to(settings.server_audio_path.resolve()):
        return jsonify({"status": "error", "message": "Invalid file path"}), 400

    file.save(str(audio_path))

    # Verify checksum if provided
    if checksum:
        h = hashlib.sha256()
        with open(audio_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        actual_checksum = h.hexdigest()
        if actual_checksum != checksum:
            logger.warning(f"Audio checksum mismatch: expected {checksum}, got {actual_checksum}")

    # Insert into database
    chunk_id = sql_store.insert_audio_chunk(
        file_path=str(audio_path),
        timestamp=timestamp,
        device_name=device_name,
        checksum=checksum,
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if chunk_id:
        return jsonify({
            "status": "accepted",
            "chunk_id": chunk_id,
            "message": "Audio chunk queued for processing",
            "elapsed_ms": round(elapsed_ms, 1),
        }), 202
    else:
        logger.error(
            "Audio upload DB insert failed | path=%s | checksum=%s",
            settings.db_path,
            checksum or "<none>",
        )
        return jsonify({
            "status": "error",
            "message": "Failed to insert audio chunk",
        }), 500


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
        for item in results:
            flat = None

            # Newer search engine result shape: dict with snapshot/video_data/audio_data.
            if isinstance(item, dict):
                snap = item.get("snapshot")
                if snap is not None:
                    flat = {
                        "id": snap.id,
                        "timestamp": snap.context.timestamp,
                        "app_name": snap.context.app_name,
                        "window_title": snap.context.window_title,
                        "caption": snap.content.caption,
                        "scene_tag": snap.content.scene_tag,
                        "image_path": snap.image_path,
                        # Phase 1.5 additive optional fields (None when unknown/unavailable)
                        "focused": None,
                        "browser_url": None,
                    }
                elif item.get("source") == "audio_transcription":
                    audio_data = item.get("audio_data") or {}
                    flat = {
                        "id": f"atranscription:{audio_data.get('id')}",
                        "timestamp": float(audio_data.get("timestamp") or 0.0),
                        "app_name": audio_data.get("device_name") or "audio",
                        "window_title": audio_data.get("transcription") or "",
                        "caption": audio_data.get("snippet") or audio_data.get("transcription") or "",
                        "scene_tag": "audio_transcription",
                        "image_path": "",
                        "focused": None,
                        "browser_url": None,
                    }
                else:
                    video_data = item.get("video_data") or {}
                    frame_id = video_data.get("frame_id")
                    flat = {
                        "id": f"vframe:{frame_id}" if frame_id is not None else "vframe:unknown",
                        "timestamp": float(video_data.get("timestamp") or 0.0),
                        "app_name": video_data.get("app_name") or "",
                        "window_title": video_data.get("window_name") or "",
                        "caption": video_data.get("text_snippet") or "",
                        "scene_tag": "video_frame",
                        "image_path": f"/api/v1/frames/{frame_id}" if frame_id is not None else "",
                        "focused": video_data.get("focused"),
                        "browser_url": video_data.get("browser_url"),
                    }
            else:
                # Legacy shape: SemanticSnapshot object.
                flat = {
                    "id": item.id,
                    "timestamp": item.context.timestamp,
                    "app_name": item.context.app_name,
                    "window_title": item.context.window_title,
                    "caption": item.content.caption,
                    "scene_tag": item.content.scene_tag,
                    "image_path": item.image_path,
                    "focused": None,
                    "browser_url": None,
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
            video_status_counts = sql_store.get_video_chunk_status_counts(conn)
            audio_status_counts = sql_store.get_audio_chunk_status_counts(conn)

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
            "audio_queue": {
                "pending": audio_status_counts.get("PENDING", 0),
                "processing": audio_status_counts.get("PROCESSING", 0),
                "completed": audio_status_counts.get("COMPLETED", 0),
                "failed": audio_status_counts.get("FAILED", 0),
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


@api_v1_bp.route("/vision/status", methods=["GET"])
@require_auth
def vision_status():
    """Read-only capture health endpoint."""
    with runtime_settings._lock:
        return jsonify(_build_vision_status()), 200


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


# =========================================================================
# Phase 1: Timeline API
# =========================================================================

@api_v1_bp.route("/timeline", methods=["GET"])
@require_auth
def timeline_api():
    """Get unified timeline entries (video frames + audio transcriptions) within a time range."""
    try:
        start_time = float(request.args.get("start_time", 0))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "start_time must be a number"}), 400
    try:
        end_time = float(request.args.get("end_time", time.time()))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "end_time must be a number"}), 400

    limit, offset = _parse_pagination()
    source_filter = request.args.get("source", "").strip().lower()

    try:
        fetch_limit = limit + offset

        frames = []
        frames_total = 0
        transcriptions = []
        trans_total = 0

        # Video frames (unless filtered to audio only)
        if source_filter not in ("audio", "audio_transcription"):
            frames, frames_total = sql_store.query_frames_by_time_range(
                start_time=start_time,
                end_time=end_time,
                limit=fetch_limit,
                offset=0,
            )
            for f in frames:
                f["type"] = "video_frame"

        # Audio transcriptions (unless filtered to video only)
        if source_filter not in ("video", "video_frame"):
            try:
                transcriptions, trans_total = sql_store.get_audio_transcriptions_by_time_range(
                    start_time=start_time,
                    end_time=end_time,
                    limit=fetch_limit,
                    offset=0,
                )
                for t in transcriptions:
                    t["type"] = "audio_transcription"
            except Exception:
                logger.debug("Audio transcriptions query failed (table may not exist yet)")

        # Merge and sort by timestamp descending
        merged = frames + transcriptions
        merged.sort(key=lambda x: float(x.get("timestamp", 0)), reverse=True)

        total = frames_total + trans_total
        page = merged[offset: offset + limit]

        return jsonify(_paginate_response(page, total, limit, offset)), 200
    except Exception as e:
        logger.exception("Error fetching timeline")
        return jsonify({"status": "error", "message": str(e)}), 500


# =========================================================================
# Phase 1: Frame Serving API
# =========================================================================

@api_v1_bp.route("/frames/<int:frame_id>", methods=["GET"])
@require_auth
def serve_frame(frame_id):
    """Serve a frame image by its database ID."""
    # Check if frame exists in DB
    frame = sql_store.get_frame_by_id(frame_id)
    if frame is None:
        return jsonify({"status": "error", "message": "Frame not found"}), 404

    # Primary path: pre-extracted PNG
    frame_filename = f"{frame_id}.png"
    frame_path = settings.frames_path / frame_filename

    if frame_path.exists():
        return send_from_directory(str(settings.frames_path), frame_filename)

    # Fallback: on-demand extraction
    try:
        from openrecall.server.video.frame_extractor import FrameExtractor
        extractor = FrameExtractor()
        chunk_path = frame.get("chunk_path", "")
        offset_index = frame.get("offset_index", 0)
        offset_seconds = offset_index * settings.frame_extraction_interval

        extracted_path = extractor.extract_single_frame(chunk_path, offset_seconds)
        if extracted_path and extracted_path.exists():
            # Rename to expected path
            extracted_path.rename(frame_path)
            return send_from_directory(str(settings.frames_path), frame_filename)
    except Exception as e:
        logger.error(f"On-demand frame extraction failed for frame {frame_id}: {e}")

    return jsonify({"status": "error", "message": "Frame image not available"}), 404


# =========================================================================
# Phase 1: Upload Status (for resume support)
# =========================================================================

@api_v1_bp.route("/upload/status", methods=["GET"])
@require_auth
def upload_status():
    """Check upload status for resume support."""
    checksum_raw = request.args.get("checksum", "").strip()
    checksum = checksum_raw.split(":", 1)[1] if checksum_raw.startswith("sha256:") else checksum_raw
    if not checksum:
        return jsonify({"status": "error", "message": "checksum required"}), 400

    video_path = settings.video_chunks_path / f"{checksum}.mp4"
    partial_path = video_path.with_suffix(".mp4.partial")

    if video_path.exists():
        return jsonify({"status": "completed", "bytes_received": video_path.stat().st_size}), 200
    elif partial_path.exists():
        return jsonify({"status": "partial", "bytes_received": partial_path.stat().st_size}), 200
    else:
        return jsonify({"status": "not_found", "bytes_received": 0}), 200


# =========================================================================
# Phase 2: Audio API endpoints
# =========================================================================

@api_v1_bp.route("/audio/chunks", methods=["GET"])
@require_auth
def audio_chunks():
    """List audio chunks with optional status filter and pagination."""
    limit, offset = _parse_pagination()
    status_filter = request.args.get("status")

    try:
        import sqlite3
        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if status_filter:
                cursor.execute(
                    "SELECT COUNT(*) FROM audio_chunks WHERE status=?",
                    (status_filter.upper(),),
                )
                total = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT * FROM audio_chunks WHERE status=? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (status_filter.upper(), limit, offset),
                )
            else:
                cursor.execute("SELECT COUNT(*) FROM audio_chunks")
                total = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT * FROM audio_chunks ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )

            chunks = [dict(row) for row in cursor.fetchall()]

        return jsonify(_paginate_response(chunks, total, limit, offset)), 200
    except Exception as e:
        logger.exception("Error fetching audio chunks")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_v1_bp.route("/audio/transcriptions", methods=["GET"])
@require_auth
def audio_transcriptions():
    """List audio transcriptions with optional time range and device filter."""
    limit, offset = _parse_pagination()

    try:
        start_time = float(request.args.get("start_time", 0))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "start_time must be a number"}), 400
    try:
        end_time = float(request.args.get("end_time", time.time()))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "end_time must be a number"}), 400

    device = request.args.get("device")

    try:
        transcriptions, total = sql_store.get_audio_transcriptions_by_time_range(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
            device=device,
        )

        return jsonify(_paginate_response(transcriptions, total, limit, offset)), 200
    except Exception as e:
        logger.exception("Error fetching audio transcriptions")
        return jsonify({"status": "error", "message": str(e)}), 500
