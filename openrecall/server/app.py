import os
import logging
from threading import Thread
from datetime import datetime
from pathlib import Path

import numpy as np
from flask import Flask, render_template, request, send_from_directory

from openrecall.shared.config import settings
from openrecall.server.api import api_bp, get_search_engine
from openrecall.server.api_v1 import v1_bp
from openrecall.server.database import SQLStore
from openrecall.server.database.frames_store import FramesStore
from openrecall.shared.utils import human_readable_time, timestamp_to_human_readable

logger = logging.getLogger(__name__)

# Initialize Store
sql_store = SQLStore()
frames_store = FramesStore()

app = Flask(__name__)

# Register API Blueprints
app.register_blueprint(api_bp)
app.register_blueprint(v1_bp)

app.jinja_env.filters["human_readable_time"] = human_readable_time
app.jinja_env.filters["timestamp_to_human_readable"] = timestamp_to_human_readable


def format_time(timestamp):
    """Format timestamp to readable time string."""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


app.jinja_env.filters["datetime"] = format_time


@app.context_processor
def inject_settings():
    """Make settings available to all templates automatically."""
    return {"settings": settings}


@app.route("/")
def index():
    """Grid view - default landing page."""
    entries = frames_store.get_recent_memories(limit=500)

    # Calculate counts
    stats = {
        "completed": sum(1 for e in entries if e.get("status") == "COMPLETED"),
        "pending": sum(
            1 for e in entries if e.get("status") in {"PENDING", "CANCELLED"}
        ),
        "processing": sum(1 for e in entries if e.get("status") == "PROCESSING"),
    }

    serialized_entries = entries

    return render_template("index.html", entries=serialized_entries, stats=stats)


@app.route("/timeline")
def timeline():
    """Timeline slider view - preserved from original."""
    timeline_frames = frames_store.get_timeline_frames(limit=5000)
    return render_template("timeline.html", timeline_frames=timeline_frames)


@app.route("/search")
def search():
    """Legacy Search UI calling New Hybrid Search Engine."""
    q = (request.args.get("q") or "").strip()

    if not q:
        # Default view: show recent entries
        entries = sql_store.get_all_entries_with_status()
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        serialized_entries = [
            {
                "id": entry.id,
                "timestamp": entry.timestamp,
                "app": entry.app,
                "title": entry.title,
                "description": entry.description,
                "status": entry.status,
                "filename": f"{entry.timestamp}.png",
                "app_name": entry.app,
                "window_title": entry.title,
                "final_rank": None,
                "final_score": None,
                "vector_rank": None,
                "vector_score": None,
                "fts_rank": None,
                "fts_bm25": None,
                "rerank_rank": None,
                "rerank_score": None,
                "combined_rank": None,
            }
            for entry in entries[:50]
        ]
        return render_template("search.html", entries=serialized_entries)

    # Use the new Hybrid Search Engine
    try:
        entries = get_search_engine().search_debug(q, limit=50)
        return render_template("search.html", entries=entries)

    except Exception as e:
        logger.error(f"Search UI failed: {e}")
        return render_template("search.html", entries=[], error=str(e))


@app.route("/static/<filename>")
def serve_image(filename):
    return send_from_directory(str(settings.screenshots_path), filename)


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    """Serve screenshot images from the screenshots directory."""
    return send_from_directory(str(settings.screenshots_path), filename)


@app.route("/vendor/<path:filename>")
def serve_vendor_asset(filename):
    vendor_dir = Path(__file__).resolve().parent / "vendor"
    return send_from_directory(str(vendor_dir), filename)


def init_background_worker(app_instance):
    """Initialize the background processing worker with crash recovery.

    This function:
    1. Recovers 'zombie' tasks stuck in PROCESSING state from crashes
    2. Starts the background worker thread
    3. Attaches worker to app instance to prevent garbage collection

    Args:
        app_instance: Flask app instance to attach worker to
    """
    # Import here to avoid circular dependency
    from openrecall.server.worker import ProcessingWorker

    # Step 1: Zombie Recovery - Fix tasks left in PROCESSING from previous crash
    count = sql_store.reset_stuck_tasks()
    if count > 0:
        logger.warning(
            f"⚠️ Recovered {count} stuck tasks (Zombies) from previous session."
        )

    # Step 2: Start the Engine
    worker = ProcessingWorker()
    worker.daemon = True  # Ensure it dies when main process dies
    worker.start()

    # Step 3: Attach to App (Crucial: Prevents Garbage Collection)
    app_instance.worker = worker
    logger.info("🚀 Background Processing Worker started successfully.")

    # Step 4: Start DescriptionWorker if enabled
    if settings.description_enabled:
        from openrecall.server.database.frames_store import FramesStore
        from openrecall.server.description.worker import DescriptionWorker

        description_store = FramesStore()
        description_worker = DescriptionWorker(description_store)
        description_worker.start()
        app_instance.description_worker = description_worker
        logger.info("DescriptionWorker started (legacy mode)")


@app.after_request
def add_cors_headers(response):
    """Allow cross-origin requests from the client web UI.

    Echoes back the Origin header so browsers can access Edge API from any origin.
    In same-machine mode: Origin = http://localhost:8883 (or 127.0.0.1)
    In distributed mode: Origin = http://<client-ip>:8883

    The Edge API itself is still protected by other auth mechanisms (future work).
    """
    request_origin = request.headers.get('Origin', '')

    # Echo back the requesting origin if present, otherwise allow all (for direct curl/etc)
    if request_origin:
        response.headers["Access-Control-Allow-Origin"] = request_origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
