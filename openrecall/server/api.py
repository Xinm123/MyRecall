"""REST API Blueprint for OpenRecall server.

Provides HTTP endpoints for client-server communication:
- Health check endpoint
- Fast screenshot ingestion endpoint (async processing)
"""

import hashlib
import logging
import time
import json
import threading
from pathlib import Path

import numpy as np
from flask import Blueprint, jsonify, request
from PIL import Image
from pydantic import ValidationError

from openrecall.server.database import SQLStore
from openrecall.server.config_runtime import runtime_settings


def _serialize_validation_errors(errors: list) -> list:
    """Convert Pydantic validation errors to JSON-serializable format."""
    result = []
    for err in errors:
        serialized = {
            "type": err.get("type"),
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "input": str(err.get("input")) if err.get("input") is not None else None,
        }
        if "ctx" in err and isinstance(err["ctx"], dict):
            ctx = err["ctx"]
            if "error" in ctx:
                serialized["ctx"] = {"error": str(ctx["error"])}
        result.append(serialized)
    return result


from openrecall.shared.config import settings
from openrecall.server.search.engine import SearchEngine
from openrecall.server.utils.auth import AuthError, require_device_auth
from openrecall.shared.contract_m0 import (
    CONTRACT_VERSION,
    DRIFT_THRESHOLD_MS,
    UploadMetadataV1,
    DriftInfo,
    HeartbeatRequestV1,
    generate_diagnostic_id,
    compute_idempotency_key,
    LEGACY_DEVICE_ID,
    MAX_UPLOAD_BYTES,
)

logger = logging.getLogger(__name__)


class TokenBucket:
    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: float = 1.0) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class DeviceRateLimiter:
    def __init__(self, rps: int):
        self.rps = rps
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()

    def check(self, device_id: str) -> bool:
        with self.lock:
            if device_id not in self.buckets:
                self.buckets[device_id] = TokenBucket(
                    rate=float(self.rps), capacity=float(self.rps)
                )
            return self.buckets[device_id].consume()


upload_rate_limiter = DeviceRateLimiter(settings.rate_limit_upload_rps)


api_bp = Blueprint("api", __name__, url_prefix="/api")
sql_store = SQLStore()
search_engine = SearchEngine()


@api_bp.route("/search", methods=["GET"])
def search_api():
    """Hybrid Search Endpoint with M0 contract support.

    Query Params:
        q: Search query string
        limit: Max results (default 50, max 200)
        device_id: Optional device filter (isolation rules apply)
        start_ts_ms: Optional start time filter (epoch ms)
        end_ts_ms: Optional end time filter (epoch ms)

    Auth Isolation Rules (M0 Plan Section 2.5):
        - With Authorization header: device_id must match token's device, or 403
        - Without Authorization: device_id is optional, allows cross-device aggregation

    Returns:
        JSON list with flattened SemanticSnapshot fields + device_id/client_ts.
    """
    diagnostic_id = generate_diagnostic_id()

    q = (request.args.get("q") or "").strip()
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50

    requested_device_id = request.args.get("device_id")
    start_ts_ms_str = request.args.get("start_ts_ms")
    end_ts_ms_str = request.args.get("end_ts_ms")

    start_ts_ms = None
    end_ts_ms = None
    if start_ts_ms_str:
        try:
            start_ts_ms = int(start_ts_ms_str)
        except ValueError:
            pass
    if end_ts_ms_str:
        try:
            end_ts_ms = int(end_ts_ms_str)
        except ValueError:
            pass

    if not q:
        return jsonify([]), 200

    auth_header = request.headers.get("Authorization")
    resolved_device_id = None

    if auth_header:
        try:
            from openrecall.server.utils.auth import (
                AuthError,
                parse_bearer_token,
                resolve_device_from_token,
            )

            token = parse_bearer_token(auth_header)
            if not token:
                return jsonify(
                    {
                        "status": "error",
                        "code": "AUTH_UNAUTHORIZED",
                        "message": "Invalid Authorization header format",
                        "diagnostic_id": diagnostic_id,
                    }
                ), 401

            token_device = resolve_device_from_token(token)
            if not token_device:
                return jsonify(
                    {
                        "status": "error",
                        "code": "AUTH_UNAUTHORIZED",
                        "message": "Invalid or unknown token",
                        "diagnostic_id": diagnostic_id,
                    }
                ), 401

            if requested_device_id and requested_device_id != token_device:
                return jsonify(
                    {
                        "status": "error",
                        "code": "AUTH_FORBIDDEN",
                        "message": f"Token belongs to device '{token_device}', cannot search device '{requested_device_id}'",
                        "diagnostic_id": diagnostic_id,
                    }
                ), 403

            resolved_device_id = requested_device_id or token_device

        except Exception as e:
            logger.exception("Auth error in search")
            return jsonify(
                {
                    "status": "error",
                    "code": "AUTH_ERROR",
                    "message": str(e),
                    "diagnostic_id": diagnostic_id,
                }
            ), 500
    else:
        resolved_device_id = requested_device_id

    try:
        results = search_engine.search(q, limit=limit, device_id=resolved_device_id)

        serialized = []
        for snap in results:
            item = snap.model_dump()

            result_device_id = (
                getattr(snap, "device_id", None)
                or resolved_device_id
                or LEGACY_DEVICE_ID
            )
            client_ts = int(snap.context.timestamp * 1000)

            flat = {
                "id": snap.id,
                "timestamp": snap.context.timestamp,
                "app_name": snap.context.app_name,
                "window_title": snap.context.window_title,
                "caption": snap.content.caption,
                "scene_tag": snap.content.scene_tag,
                "image_path": snap.image_path,
                "device_id": result_device_id,
                "client_ts": client_ts,
                "full_data": item,
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

        processing_mode = (
            "LIFO" if pending > settings.processing_lifo_threshold else "FIFO"
        )

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
                "reranker_mode": settings.reranker_mode,
                "reranker_model": settings.reranker_model,
            },
        }

        return jsonify(response), 200
    except Exception as e:
        logger.exception("Error getting queue status")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/upload", methods=["POST"])
def upload():
    """Fast screenshot ingestion endpoint with M0 contract support.

    Accepts multipart/form-data:
    - file: Image file (PNG)
    - metadata: JSON string with M0 contract fields

    Returns:
        HTTP 202 (new upload), 200 (idempotent replay), 409 (conflict),
        401 (missing auth), 403 (forbidden), 413 (too large), 422 (hash mismatch)
    """
    start_time = time.perf_counter()
    diagnostic_id = generate_diagnostic_id()
    server_received_at = int(time.time() * 1000)

    if "file" not in request.files:
        return jsonify(
            {
                "status": "error",
                "code": "MISSING_FILE",
                "message": "No file part",
                "diagnostic_id": diagnostic_id,
            }
        ), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify(
            {
                "status": "error",
                "code": "EMPTY_FILENAME",
                "message": "No selected file",
                "diagnostic_id": diagnostic_id,
            }
        ), 400

    file_bytes = file.read()
    file_size = len(file_bytes)

    max_upload_bytes = getattr(settings, "max_upload_bytes", MAX_UPLOAD_BYTES)
    if file_size > max_upload_bytes:
        return jsonify(
            {
                "status": "error",
                "code": "UPLOAD_TOO_LARGE",
                "message": f"File size {file_size} exceeds limit {max_upload_bytes}",
                "diagnostic_id": diagnostic_id,
            }
        ), 413

    metadata_str = request.form.get("metadata")
    if not metadata_str:
        return jsonify(
            {
                "status": "error",
                "code": "MISSING_METADATA",
                "message": "No metadata provided",
                "diagnostic_id": diagnostic_id,
            }
        ), 400

    try:
        metadata_dict = json.loads(metadata_str)
    except json.JSONDecodeError as e:
        return jsonify(
            {
                "status": "error",
                "code": "INVALID_JSON",
                "message": f"Invalid JSON in metadata: {e}",
                "diagnostic_id": diagnostic_id,
            }
        ), 400

    try:
        metadata = UploadMetadataV1.model_validate(metadata_dict)
    except ValidationError as e:
        return jsonify(
            {
                "status": "error",
                "code": "VALIDATION_ERROR",
                "message": "Metadata validation failed",
                "diagnostic_id": diagnostic_id,
                "details": _serialize_validation_errors(e.errors()),
            }
        ), 400

    try:
        device_id, auth_mode = require_device_auth(
            request.headers.get("Authorization"), metadata.device_id
        )
    except AuthError as e:
        return jsonify(
            {
                "status": "error",
                "code": e.code,
                "message": e.message,
                "diagnostic_id": diagnostic_id,
            }
        ), e.status_code

    if not upload_rate_limiter.check(device_id):
        logger.warning(
            f"Rate limit exceeded: device={device_id}, diagnostic_id={diagnostic_id}"
        )
        return jsonify(
            {
                "status": "error",
                "code": "RATE_LIMITED",
                "message": "Upload rate limit exceeded",
                "diagnostic_id": diagnostic_id,
            }
        ), 429

    computed_hash = hashlib.sha256(file_bytes).hexdigest()
    if computed_hash != metadata.image_hash:
        return jsonify(
            {
                "status": "error",
                "code": "UPLOAD_HASH_MISMATCH",
                "message": "Computed hash does not match provided hash",
                "diagnostic_id": diagnostic_id,
                "computed": computed_hash,
                "provided": metadata.image_hash,
            }
        ), 422

    existing = sql_store.get_entry_by_device_client_ts(device_id, metadata.client_ts)

    if existing:
        if existing["image_hash"] == metadata.image_hash:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"Idempotent replay: device={device_id}, client_ts={metadata.client_ts}, "
                f"entry_id={existing['id']}, diagnostic_id={diagnostic_id}"
            )
            return jsonify(
                {
                    "status": "ok",
                    "idempotent_replay": True,
                    "entry_id": existing["id"],
                    "task_id": existing["id"],
                    "device_id": device_id,
                    "client_ts": metadata.client_ts,
                    "server_received_at": server_received_at,
                    "original_server_received_at": existing["server_received_at"],
                    "existing_status": existing["status"],
                    "diagnostic_id": diagnostic_id,
                }
            ), 200
        else:
            logger.warning(
                f"Upload conflict: device={device_id}, client_ts={metadata.client_ts}, "
                f"existing_hash={existing['image_hash']}, incoming_hash={metadata.image_hash}, "
                f"diagnostic_id={diagnostic_id}"
            )
            return jsonify(
                {
                    "status": "conflict",
                    "code": "UPLOAD_CONFLICT",
                    "message": "Same (device_id, client_ts) but different image_hash",
                    "device_id": device_id,
                    "client_ts": metadata.client_ts,
                    "existing": {
                        "entry_id": existing["id"],
                        "image_hash": existing["image_hash"],
                    },
                    "incoming": {"image_hash": metadata.image_hash},
                    "diagnostic_id": diagnostic_id,
                }
            ), 409

    device_dir = settings.screenshots_path / device_id
    device_dir.mkdir(parents=True, exist_ok=True)

    image_filename = f"{metadata.client_ts}_{metadata.image_hash[:8]}.png"
    image_path = device_dir / image_filename
    image_relpath = f"{device_id}/{image_filename}"

    with open(image_path, "wb") as f:
        f.write(file_bytes)

    timestamp = metadata.client_ts // 1000

    try:
        entry_id = sql_store.insert_pending_entry_v1(
            device_id=device_id,
            client_ts=metadata.client_ts,
            client_tz=metadata.client_tz,
            client_seq=metadata.client_seq,
            image_hash=metadata.image_hash,
            app=metadata.app_name,
            title=metadata.window_title,
            image_relpath=image_relpath,
            server_received_at=server_received_at,
            timestamp=timestamp,
        )

        if not entry_id:
            return jsonify(
                {
                    "status": "error",
                    "code": "INSERT_FAILED",
                    "message": "Failed to insert entry into database",
                    "diagnostic_id": diagnostic_id,
                }
            ), 500

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        pending_count = sql_store.get_pending_count() if settings.debug else 0

        idempotency_key = compute_idempotency_key(
            device_id, metadata.client_ts, metadata.image_hash
        )

        if settings.debug:
            logger.debug(
                f"✅ HTTP 202 Accepted | entry_id={entry_id} | device={device_id} | "
                f"client_ts={metadata.client_ts} | {elapsed_ms:.1f}ms | queue={pending_count}"
            )

        response_data = {
            "status": "accepted",
            "entry_id": entry_id,
            "task_id": entry_id,
            "device_id": device_id,
            "client_ts": metadata.client_ts,
            "server_received_at": server_received_at,
            "image_hash": metadata.image_hash,
            "idempotency_key": idempotency_key,
            "queue": {"pending": pending_count},
            "diagnostic_id": diagnostic_id,
        }

        return jsonify(response_data), 202

    except Exception as e:
        logger.exception(f"Upload ingestion error: diagnostic_id={diagnostic_id}")
        return jsonify(
            {
                "status": "error",
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "diagnostic_id": diagnostic_id,
            }
        ), 500


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
        "ui_show_ai",
    }

    try:
        with runtime_settings._lock:
            for field, value in data.items():
                if field not in valid_fields:
                    return jsonify(
                        {"status": "error", "message": f"Unknown field: {field}"}
                    ), 400

                if not isinstance(value, bool):
                    return jsonify(
                        {"status": "error", "message": f"Field {field} must be boolean"}
                    ), 400

                # Special handling for ai_processing_enabled:
                if (
                    field == "ai_processing_enabled"
                    and not value
                    and getattr(runtime_settings, field)
                ):
                    logger.info(
                        "AI processing disabled: Will stop picking up new tasks"
                    )
                    sql_store.cancel_processing_tasks()
                    runtime_settings.ai_processing_version += 1
                if (
                    field == "ai_processing_enabled"
                    and value
                    and not getattr(runtime_settings, field)
                ):
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
    diagnostic_id = generate_diagnostic_id()
    try:
        payload = request.get_json(silent=True)
        heartbeat_data = None
        requested_device_id = LEGACY_DEVICE_ID
        if isinstance(payload, dict):
            try:
                heartbeat_data = HeartbeatRequestV1.model_validate(payload)
            except ValidationError as exc:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "code": "HEARTBEAT_VALIDATION_ERROR",
                            "message": "Invalid heartbeat payload",
                            "diagnostic_id": diagnostic_id,
                            "details": _serialize_validation_errors(exc.errors()),
                        }
                    ),
                    400,
                )
            requested_device_id = heartbeat_data.device_id

        try:
            resolved_device_id, auth_mode = require_device_auth(
                request.headers.get("Authorization"),
                requested_device_id=requested_device_id,
            )
        except AuthError as exc:
            return (
                jsonify(
                    {
                        "status": "error",
                        "code": exc.code,
                        "message": exc.message,
                        "diagnostic_id": diagnostic_id,
                        "server_received_at": int(time.time() * 1000),
                    }
                ),
                exc.status_code,
            )

        with runtime_settings._lock:
            runtime_settings.last_heartbeat = time.time()
            config = runtime_settings.to_dict()
            client_online = (time.time() - runtime_settings.last_heartbeat) < 15
            config["client_online"] = client_online

        if heartbeat_data is None:
            return jsonify({"status": "ok", "config": config}), 200

        server_time_ms = int(time.time() * 1000)
        drift_ms = server_time_ms - heartbeat_data.client_ts
        drift_exceeded = abs(drift_ms) > DRIFT_THRESHOLD_MS
        if drift_exceeded:
            logger.warning(
                "Heartbeat drift exceeded threshold: device_id=%s drift_ms=%s threshold_ms=%s",
                resolved_device_id,
                drift_ms,
                DRIFT_THRESHOLD_MS,
            )

        drift_info = DriftInfo(
            estimate=drift_ms,
            exceeded=drift_exceeded,
            threshold=DRIFT_THRESHOLD_MS,
        ).model_dump()

        response = {
            "status": "ok",
            "server_time_ms": server_time_ms,
            "config": config,
            "drift_ms": drift_info,
            "server_capabilities": {
                "contract_version": CONTRACT_VERSION,
                "time_unit": "ms",
                "auth_mode": auth_mode,
                "token_rotation": {
                    "grace_seconds": settings.token_grace_seconds,
                },
            },
            "diagnostic_id": diagnostic_id,
        }

        return jsonify(response), 200
    except Exception as e:
        logger.exception("Error processing heartbeat")
        return (
            jsonify(
                {"status": "error", "message": str(e), "diagnostic_id": diagnostic_id}
            ),
            500,
        )
