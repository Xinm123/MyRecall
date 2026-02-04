"""REST API v3 Blueprint for OpenRecall server.

v3 API provides:
- GET /api/v3/frames - Paginated frames for timeline-v3
"""

import logging
import time

from flask import Blueprint, jsonify, request

from openrecall.server.database import SQLStore

logger = logging.getLogger(__name__)

v3_bp = Blueprint("api_v3", __name__, url_prefix="/api/v3")
sql_store = SQLStore()


@v3_bp.route("/frames", methods=["GET"])
def get_frames():
    """Get frames with pagination support.

    Query Params:
        before: Return frames with timestamp < before (for pagination)
        after: Return frames with timestamp > after (for polling/incremental)
        limit: Max results (default 50, max 200)
        status: Filter by status (PENDING, COMPLETED, PROCESSING, FAILED)
        app: Filter by app name (contains match)
        window: Filter by window title (contains match)

    Returns:
        JSON:
        {
            "items": [
                {
                    "id": int,
                    "timestamp": int,
                    "app_name": str,
                    "window_title": str,
                    "description": str | null,
                    "status": str,
                    "image_url": str
                },
                ...
            ],
            "next_before": int | null,  # cursor for next page
            "server_time": int           # server timestamp for sync
        }
    """
    before = request.args.get("before", type=int)
    after = request.args.get("after", type=int)
    limit = request.args.get("limit", default=50, type=int)
    status = request.args.get("status", type=str)
    app = request.args.get("app", type=str)
    window = request.args.get("window", type=str)

    items, next_before = sql_store.get_frames(
        before=before,
        after=after,
        limit=limit,
        status=status,
        app=app,
        window=window,
    )

    return jsonify(
        {"items": items, "next_before": next_before, "server_time": int(time.time())}
    ), 200
