"""v3 API Blueprint: /v1/* endpoints for P1-S1 ingest baseline.

This module defines the v1_bp Blueprint and implements:
  - POST /v1/ingest          — idempotent single-frame upload
  - GET  /v1/ingest/queue/status — live queue counters
  - GET  /v1/frames/<frame_id>   — serve frame JPEG
  - GET  /v1/health              — health check

SSOT: docs/v3/spec.md §4.7, §4.8.1, §4.9; docs/v3/http_contract_ledger.md
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_file

from openrecall.server.config_runtime import runtime_settings
from openrecall.server.database.frames_store import FramesStore
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

v1_bp = Blueprint("v1", __name__, url_prefix="/v1")

# Module-level store instance (shared across requests in the same process)
_frames_store: Optional[FramesStore] = None

# Constants for validation
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_MIME_TYPE = "image/jpeg"
_ALLOWED_CAPTURE_TRIGGERS = frozenset({"idle", "app_switch", "manual", "click"})


def _get_frames_store() -> FramesStore:
    """Lazily initialize the FramesStore singleton."""
    global _frames_store
    if _frames_store is None:
        _frames_store = FramesStore()
    return _frames_store


def _parse_utc_timestamp(raw_value: str | None) -> datetime | None:
    if raw_value is None:
        return None

    normalized = raw_value.strip().replace(" ", "T")
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    elif "+" not in normalized and "-" not in normalized[10:]:
        normalized = f"{normalized}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Error response helper
# ---------------------------------------------------------------------------


def make_error_response(
    error_msg: str,
    code: str,
    status_code: int,
    request_id: Optional[str] = None,
    **extra,
):
    """Build a uniform JSON error response.

    Args:
        error_msg: Human-readable error description.
        code: Machine-readable error code (e.g. ``INVALID_PARAMS``).
        status_code: HTTP status code to use.
        request_id: Optional UUID v4; auto-generated when omitted.
        **extra: Additional key-value pairs to merge into the response body.

    Returns:
        A (flask.Response, int) tuple suitable for returning from a route.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())

    body: dict[str, object] = {
        "error": error_msg,
        "code": code,
        "request_id": request_id,
    }
    body.update(extra)
    return jsonify(body), status_code


# ---------------------------------------------------------------------------
# POST /v1/ingest
# ---------------------------------------------------------------------------


@v1_bp.route("/ingest", methods=["POST"])
def ingest():
    """Idempotent single-frame ingest endpoint.

    Multipart fields:
        capture_id  – UUID v7 string (required)
        metadata    – JSON string (required, may be ``{}``)
        file        – JPEG binary (required, <= 10 MB)

    Success:
        201 Created       → new frame   {"capture_id", "frame_id", "status": "queued",       "request_id"}
        200 OK            → duplicate   {"capture_id", "frame_id", "status": "already_exists","request_id"}

    Errors (no DB writes on 400/413/503):
        400 INVALID_PARAMS     — missing / malformed fields
        413 PAYLOAD_TOO_LARGE  — file > 10 MB
        503 QUEUE_FULL         — pending >= capacity
        500 INTERNAL_ERROR     — unexpected server failure
    """
    request_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Step 1: Parse multipart fields
    # ------------------------------------------------------------------
    capture_id_raw = request.form.get("capture_id", "").strip()
    metadata_raw = request.form.get("metadata", "").strip()
    file_storage = request.files.get("file")

    # ------------------------------------------------------------------
    # Step 2: Validate required fields and formats
    # ------------------------------------------------------------------

    # capture_id must be present
    if not capture_id_raw:
        return make_error_response(
            "capture_id is required",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    try:
        parsed_capture_id = uuid.UUID(capture_id_raw)
    except ValueError:
        return make_error_response(
            f"capture_id must be a valid UUIDv7, got: {capture_id_raw!r}",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    if parsed_capture_id.version != 7 or parsed_capture_id.variant != uuid.RFC_4122:
        return make_error_response(
            "capture_id must be UUIDv7",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    # file must be present
    if file_storage is None or file_storage.filename == "":
        return make_error_response(
            "file is required",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    # MIME type must be image/jpeg
    content_type = file_storage.content_type or ""

    # Strip parameters, e.g. "image/jpeg; charset=..."
    mime_type = content_type.split(";")[0].strip().lower()
    if mime_type != _ALLOWED_MIME_TYPE:
        return make_error_response(
            f"file must be image/jpeg, got: {content_type!r}",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    # Read file bytes (needed for size check and persistence)
    file_bytes = file_storage.read()

    # Size check — must come AFTER reading; 413 must not write to DB
    if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
        return make_error_response(
            f"file exceeds maximum size of {_MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB",
            "PAYLOAD_TOO_LARGE",
            413,
            request_id=request_id,
        )

    # metadata JSON parse (optional fields; empty string → {})
    metadata: dict[str, object] = {}
    if metadata_raw:
        try:
            metadata = json.loads(metadata_raw)
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            return make_error_response(
                f"metadata must be valid JSON: {exc}",
                "INVALID_PARAMS",
                400,
                request_id=request_id,
            )

    capture_trigger = metadata.get("capture_trigger")
    if (
        capture_trigger is None
        or not isinstance(capture_trigger, str)
        or capture_trigger not in _ALLOWED_CAPTURE_TRIGGERS
    ):
        return make_error_response(
            "capture_trigger must be one of idle, app_switch, manual, click",
            "INVALID_PARAMS",
            400,
            request_id=request_id,
        )

    # ------------------------------------------------------------------
    # Step 3: Back-pressure check (503) — no DB writes before this point
    # ------------------------------------------------------------------
    store = _get_frames_store()
    capacity = settings.queue_capacity
    try:
        pending = store.get_pending_count()
    except Exception as exc:
        logger.exception("ingest: get_pending_count failed: %s", exc)
        return make_error_response(
            "Failed to query queue status",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )

    if pending >= capacity:
        return make_error_response(
            "Queue is full, retry later",
            "QUEUE_FULL",
            503,
            request_id=request_id,
            retry_after=30,
        )

    metadata.setdefault("image_size_bytes", len(file_bytes))

    try:
        frame_id, is_new = store.claim_frame(
            capture_id=capture_id_raw,
            metadata=metadata,
        )
    except Exception as exc:
        logger.exception(
            "ingest: claim_frame failed capture_id=%s: %s", capture_id_raw, exc
        )
        return make_error_response(
            "Failed to store frame metadata",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )

    if not is_new:
        logger.debug(
            "ingest: 200 already_exists capture_id=%s frame_id=%d request_id=%s",
            capture_id_raw,
            frame_id,
            request_id,
        )
        return (
            jsonify(
                {
                    "capture_id": capture_id_raw,
                    "frame_id": frame_id,
                    "status": "already_exists",
                    "request_id": request_id,
                }
            ),
            200,
        )

    frames_dir = settings.frames_dir
    frames_dir.mkdir(parents=True, exist_ok=True)
    snapshot_filename = f"{capture_id_raw}.jpg"
    snapshot_path = frames_dir / snapshot_filename

    # ------------------------------------------------------------------
    # Step 4a: Check for accessibility-canonical payload
    # ------------------------------------------------------------------
    if (
        metadata.get("text_source") == "accessibility"
        and "accessibility" in metadata
        and isinstance(metadata.get("accessibility"), dict)
    ):
        try:
            return _handle_accessibility_canonical_ingest(
                store=store,
                frame_id=frame_id,
                capture_id=capture_id_raw,
                metadata=metadata,
                snapshot_path=snapshot_path,
                file_bytes=file_bytes,
                request_id=request_id,
            )
        except Exception as exc:
            # Log and degrade to OCR-pending
            logger.warning(
                "ingest: accessibility payload invalid, degrading to OCR-pending: %s",
                exc,
            )
            # Fall through to normal pending path

    # ------------------------------------------------------------------
    # Step 5: Persist JPEG and finalize as pending (OCR path)
    # ------------------------------------------------------------------
    try:
        tmp_path = snapshot_path.with_suffix(f".jpg.{request_id}.tmp")
        tmp_path.write_bytes(file_bytes)
        tmp_path.replace(snapshot_path)
        finalized = store.finalize_claimed_frame(
            frame_id=frame_id,
            capture_id=capture_id_raw,
            snapshot_path=str(snapshot_path),
        )
        if not finalized:
            raise RuntimeError("failed to finalize claimed frame")
    except Exception as exc:
        logger.exception(
            "ingest: failed to persist/finalize capture_id=%s frame_id=%d: %s",
            capture_id_raw,
            frame_id,
            exc,
        )
        try:
            if snapshot_path.exists():
                snapshot_path.unlink(missing_ok=True)
        except OSError:
            pass
        store.delete_unfinalized_claim(frame_id=frame_id, capture_id=capture_id_raw)
        return make_error_response(
            "Failed to persist frame image",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )

    # ------------------------------------------------------------------
    # Step 6: Build success response (2xx — no "code" field)
    # ------------------------------------------------------------------
    logger.info(
        "ingest: 201 Created capture_id=%s frame_id=%d request_id=%s",
        capture_id_raw,
        frame_id,
        request_id,
    )
    return (
        jsonify(
            {
                "capture_id": capture_id_raw,
                "frame_id": frame_id,
                "status": "queued",
                "request_id": request_id,
            }
        ),
        201,
    )


def _handle_accessibility_canonical_ingest(
    store: FramesStore,
    frame_id: int,
    capture_id: str,
    metadata: dict,
    snapshot_path: Path,
    file_bytes: bytes,
    request_id: str,
):
    """Handle ingest for accessibility-canonical frames.

    This function processes frames that have accessibility data and
    completes them synchronously without OCR processing.

    Args:
        store: FramesStore instance
        frame_id: The claimed frame ID
        capture_id: The capture UUID
        metadata: The frame metadata dict
        snapshot_path: Path to save the JPEG
        file_bytes: The JPEG file bytes
        request_id: Request ID for logging

    Returns:
        Flask response tuple

    Raises:
        ValueError: If accessibility payload is malformed
    """
    acc = metadata.get("accessibility")
    if not isinstance(acc, dict):
        raise ValueError("accessibility payload must be a dict")

    # Validate required fields
    if "tree_json" not in acc:
        raise ValueError("Missing tree_json in accessibility payload")

    # Parse tree_json to validate it's valid JSON
    try:
        tree_nodes = json.loads(acc["tree_json"])
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid tree_json: {e}") from e

    if not isinstance(tree_nodes, list):
        raise ValueError("tree_json must be a JSON array")

    # Persist JPEG
    try:
        tmp_path = snapshot_path.with_suffix(f".jpg.{request_id}.tmp")
        tmp_path.write_bytes(file_bytes)
        tmp_path.replace(snapshot_path)
    except Exception as exc:
        logger.exception(
            "ingest: failed to persist JPEG capture_id=%s frame_id=%d: %s",
            capture_id,
            frame_id,
            exc,
        )
        raise RuntimeError(f"Failed to persist JPEG: {exc}") from exc

    # Finalize snapshot path
    finalized = store.finalize_claimed_frame(
        frame_id=frame_id,
        capture_id=capture_id,
        snapshot_path=str(snapshot_path),
    )
    if not finalized:
        raise RuntimeError("Failed to finalize claimed frame")

    # Complete with accessibility
    text = metadata.get("text", acc.get("text_content", ""))
    success = store.complete_accessibility_frame(
        frame_id=frame_id,
        text=str(text),
        browser_url=metadata.get("browser_url") if isinstance(metadata.get("browser_url"), str) else None,
        content_hash=metadata.get("content_hash") if isinstance(metadata.get("content_hash"), int) else None,
        simhash=metadata.get("simhash") if isinstance(metadata.get("simhash"), int) else None,
        accessibility_tree_json=acc["tree_json"],
        accessibility_text_content=acc.get("text_content", ""),
        accessibility_node_count=acc.get("node_count", 0) if isinstance(acc.get("node_count"), int) else 0,
        accessibility_truncated=acc.get("truncated", False) if isinstance(acc.get("truncated"), bool) else False,
        elements=tree_nodes,
    )

    if not success:
        raise RuntimeError("Failed to complete accessibility frame")

    logger.info(
        "ingest: 201 Created (accessibility-canonical) capture_id=%s frame_id=%d request_id=%s",
        capture_id,
        frame_id,
        request_id,
    )

    return (
        jsonify(
            {
                "capture_id": capture_id,
                "frame_id": frame_id,
                "status": "completed",
                "request_id": request_id,
            }
        ),
        201,
    )


# ---------------------------------------------------------------------------
# GET /v1/ingest/queue/status
# ---------------------------------------------------------------------------


@v1_bp.route("/ingest/queue/status", methods=["GET"])
def queue_status():
    """Return live queue counters from DB.

    Response:
        {
            "pending":                  <int>,
            "processing":               <int>,
            "completed":                <int>,
            "failed":                   <int>,
            "processing_mode":          "noop",
            "capacity":                 <int>,
            "oldest_pending_ingested_at": <ISO8601 string | null>
        }
    """
    store = _get_frames_store()
    try:
        counts = store.get_queue_counts()
        oldest = store.get_oldest_pending_ingested_at()
    except Exception as exc:
        logger.exception("queue_status: DB query failed: %s", exc)
        request_id = str(uuid.uuid4())
        return make_error_response(
            "Failed to query queue status",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )

    return jsonify(
        {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "processing_mode": settings.processing_mode,
            "capacity": settings.queue_capacity,
            "oldest_pending_ingested_at": oldest,
            "trigger_channel": runtime_settings.get_trigger_channel_snapshot(),
            "capture_latency": store.get_capture_latency_summary(),
            "status_sync": store.get_status_sync_summary(),
        }
    )


# ---------------------------------------------------------------------------
# GET /v1/frames/<frame_id>
# ---------------------------------------------------------------------------


@v1_bp.route("/frames/<int:frame_id>", methods=["GET"])
def get_frame(frame_id: int):
    """Serve the JPEG snapshot for a frame.

    Returns:
        200 image/jpeg  — JPEG binary
        404 NOT_FOUND   — frame_id not in DB, or snapshot file missing
    """
    request_id = str(uuid.uuid4())
    store = _get_frames_store()

    frame = store.get_frame(frame_id)
    if frame is None:
        return make_error_response(
            "frame not found",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    snapshot_path = frame.snapshot_path
    if not snapshot_path:
        logger.error(
            "get_frame: snapshot_path is empty for frame_id=%d (IO_ERROR)",
            frame_id,
        )
        return make_error_response(
            "frame snapshot path not set",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    path = Path(snapshot_path)
    if not path.exists():
        logger.error(
            "get_frame: snapshot file missing frame_id=%d path=%s (IO_ERROR)",
            frame_id,
            snapshot_path,
        )
        # Read-only path: must NOT call mark_failed() or any write operation
        return make_error_response(
            "frame snapshot file not found on disk",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    return send_file(str(path), mimetype="image/jpeg")


# ---------------------------------------------------------------------------
# GET /v1/frames/<frame_id>/ocr-vis
# ---------------------------------------------------------------------------


@v1_bp.route("/frames/<int:frame_id>/ocr-vis", methods=["GET"])
def get_ocr_visualization(frame_id: int):
    """Serve the OCR visualization image for a frame.

    The visualization shows the original screenshot with OCR bounding boxes
    and recognized text overlaid.

    Returns:
        200 image/jpeg  — JPEG binary with OCR boxes overlaid
        404 NOT_FOUND   — frame not found, or OCR visualization not available
    """
    request_id = str(uuid.uuid4())
    store = _get_frames_store()

    # Check frame exists and has completed OCR
    frame = store.get_frame(frame_id)
    if frame is None:
        return make_error_response(
            "frame not found",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    # Check frame status - only completed frames have OCR visualization
    if frame.status != "completed":
        return make_error_response(
            f"OCR visualization not available (status={frame.status})",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    # Build path to visualization image
    vis_path = settings.server_data_dir / "ocr_vis" / f"{frame_id}.jpg"
    if not vis_path.exists():
        return make_error_response(
            "OCR visualization file not found",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    return send_file(str(vis_path), mimetype="image/jpeg")


# ---------------------------------------------------------------------------
# GET /v1/health
# ---------------------------------------------------------------------------


@v1_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint.

    Response fields (subset of screenpipe HealthCheckResponse):
        status              — "ok" | "degraded"  (P1-S1: never "error")
        last_frame_timestamp    — ISO8601 string | null
        last_frame_ingested_at  — ISO8601 string | null
        frame_status        — "ok" | "stale"
        message             — human-readable description
        queue               — { pending, processing, failed }
    """
    store = _get_frames_store()
    try:
        last_frame_ts = store.get_last_frame_timestamp()
        last_ingested_at = store.get_last_frame_ingested_at()
        counts = store.get_queue_counts()
    except Exception as exc:
        logger.exception("health: DB query failed: %s", exc)
        request_id = str(uuid.uuid4())
        return make_error_response(
            "Failed to query health data",
            "INTERNAL_ERROR",
            500,
            request_id=request_id,
        )

    # frame_status: stale if no ingested frame yet, or last ingested >= 5 min ago
    _STALE_THRESHOLD_SECONDS = 5 * 60
    if last_ingested_at is None:
        frame_status = "stale"
    else:
        last_dt = _parse_utc_timestamp(last_ingested_at)
        if last_dt is None:
            logger.warning(
                "health: could not parse last_ingested_at=%r; treating as stale",
                last_ingested_at,
            )
            frame_status = "stale"
        else:
            now = datetime.now(tz=timezone.utc)
            age_seconds = (now - last_dt).total_seconds()
            frame_status = "stale" if age_seconds >= _STALE_THRESHOLD_SECONDS else "ok"

    failed_count = counts.get("failed", 0)
    permission_snapshot = runtime_settings.get_permission_snapshot()
    capture_runtime_snapshot = runtime_settings.get_capture_runtime_snapshot()
    permission_status = permission_snapshot["capture_permission_status"]
    permission_reason = permission_snapshot["capture_permission_reason"]
    permission_degraded = (
        permission_snapshot["is_stale"] or permission_status != "granted"
    )

    # P1-S1: status is only "ok" or "degraded"
    if failed_count > 0 or frame_status != "ok" or permission_degraded:
        overall_status = "degraded"
    else:
        overall_status = "ok"

    if overall_status == "ok":
        message = "服务健康/队列正常"
    elif permission_reason == "stale_permission_state":
        message = "权限状态陈旧"
    elif permission_status == "transient_failure":
        message = "权限待确认"
    elif permission_status == "recovering":
        message = "权限恢复中"
    elif permission_status == "denied_or_revoked":
        message = "权限异常"
    elif last_frame_ts is None and frame_status == "stale" and failed_count == 0:
        message = "等待首帧"
    elif failed_count > 0:
        message = "队列异常"
    else:
        message = "数据延迟"

    return jsonify(
        {
            "status": overall_status,
            "last_frame_timestamp": last_frame_ts,
            "last_frame_ingested_at": last_ingested_at,
            "frame_status": frame_status,
            "message": message,
            "capture_permission_status": permission_status,
            "capture_permission_reason": permission_reason,
            "last_permission_check_ts": permission_snapshot["last_permission_check_ts"],
            "queue": {
                "pending": counts.get("pending", 0),
                "processing": counts.get("processing", 0),
                "failed": failed_count,
            },
            "capture_runtime": capture_runtime_snapshot,
        }
    )


# ---------------------------------------------------------------------------
# GET /v1/search
# ---------------------------------------------------------------------------

# Module-level search engine instance
_search_engine = None


def _get_search_engine():
    """Lazily initialize the SearchEngine singleton."""
    global _search_engine
    if _search_engine is None:
        from openrecall.server.search.engine import SearchEngine

        _search_engine = SearchEngine()
    return _search_engine


@v1_bp.route("/search", methods=["GET"])
def search():
    """FTS5 full-text search endpoint.

    Query Parameters:
        q: Text query (sanitized via sanitize_fts5_query)
        limit: Max results (default 20, max 100)
        offset: Pagination offset (default 0)
        start_time: ISO8601 UTC start timestamp
        end_time: ISO8601 UTC end timestamp
        app_name: Filter by app name (exact match via FTS)
        window_name: Filter by window name (exact match via FTS)
        focused: Filter by focused state (true/false)
        min_length: Minimum OCR text length
        max_length: Maximum OCR text length
        browser_url: Accepted but no-op in P1
        include_frames: Accepted, always null in P1

    Returns:
        JSON response with search results matching spec.md §4.5.
    """
    # Parse query parameters
    q = request.args.get("q", "").strip()

    # Parse limit (default 20, max 100)
    try:
        limit = int(request.args.get("limit", 20))
    except (ValueError, TypeError):
        limit = 20
    limit = max(1, min(limit, 100))

    # Parse offset (default 0)
    try:
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        offset = 0
    offset = max(0, offset)

    # Parse time range
    start_time = request.args.get("start_time")
    if start_time:
        start_time = start_time.strip() or None

    end_time = request.args.get("end_time")
    if end_time:
        end_time = end_time.strip() or None

    # Parse metadata filters
    app_name = request.args.get("app_name")
    if app_name:
        app_name = app_name.strip() or None

    window_name = request.args.get("window_name")
    if window_name:
        window_name = window_name.strip() or None

    # Parse focused
    focused_str = request.args.get("focused")
    focused = None
    if focused_str:
        focused_lower = focused_str.strip().lower()
        if focused_lower in ("true", "1", "yes"):
            focused = True
        elif focused_lower in ("false", "0", "no"):
            focused = False

    # Parse text length
    min_length = None
    max_length = None
    try:
        min_length = int(request.args.get("min_length", 0)) or None
    except (ValueError, TypeError):
        pass
    try:
        max_length = int(request.args.get("max_length", 0)) or None
    except (ValueError, TypeError):
        pass

    # browser_url is accepted but no-op in P1
    # include_frames is accepted but always null in P1

    # Execute search
    engine = _get_search_engine()
    results, total = engine.search(
        q=q,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
        window_name=window_name,
        focused=focused,
        min_length=min_length,
        max_length=max_length,
    )

    # Build response per spec.md §4.5
    data_items = []
    for r in results:
        item = {
            "type": "OCR",
            "content": {
                "frame_id": r["frame_id"],
                "text": r.get("text", ""),
                "text_source": r.get("text_source"),
                "timestamp": r.get("timestamp"),
                "file_path": r.get("file_path", ""),
                "frame_url": r.get("frame_url", ""),
                "app_name": r.get("app_name"),
                "window_name": r.get("window_name"),
                "browser_url": None,  # Reserved, always null in P1
                "focused": r.get("focused"),
                "device_name": r.get("device_name", "monitor_0"),
                "tags": [],  # Reserved, always empty in P1
                "fts_rank": r.get("fts_rank"),  # BM25 rank (null when no text query)
            },
        }
        data_items.append(item)

    return jsonify(
        {
            "type": "OCR",
            "data": data_items,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
            },
        }
    )


# ---------------------------------------------------------------------------
# GET /v1/search/keyword - 404 Guard Route
# ---------------------------------------------------------------------------

# IMPORTANT: This route MUST be registered AFTER /v1/search to avoid shadowing
# the main search route. Flask matches routes in registration order, and
# /v1/search is a prefix that would otherwise match /v1/search/keyword.
# This is a guard route to prevent accidental implementation of an independent
# keyword endpoint (per specs/fts-search/spec.md).


@v1_bp.route("/search/keyword", methods=["GET"])
def search_keyword_404_guard():
    """Guard route that returns 404 for /v1/search/keyword.

    This endpoint is intentionally not implemented in P1. Future versions
    may add specialized keyword search functionality.

    Returns:
        404 NOT_FOUND with error JSON.
    """
    return make_error_response(
        "not found",
        "NOT_FOUND",
        404,
    )
