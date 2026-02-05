import os
import logging
from threading import Thread
from datetime import datetime
from pathlib import Path

import numpy as np
from flask import Flask, render_template, request, send_from_directory

from openrecall.shared.config import settings
from openrecall.server.api import api_bp, search_engine
from openrecall.server.database import SQLStore
from openrecall.shared.utils import human_readable_time, timestamp_to_human_readable

logger = logging.getLogger(__name__)

# Initialize Store
sql_store = SQLStore()

app = Flask(__name__)

# Register API Blueprint
app.register_blueprint(api_bp)

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
    entries = sql_store.get_all_entries_with_status()
    # Sort by timestamp descending (newest first)
    entries.sort(key=lambda x: x.timestamp, reverse=True)

    # Calculate counts
    stats = {
        "completed": sum(1 for e in entries if e.status == "COMPLETED"),
        "pending": sum(1 for e in entries if e.status == "PENDING"),
        "processing": sum(1 for e in entries if e.status == "PROCESSING"),
    }

    serialized_entries = [
        {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "app": entry.app,
            "title": entry.title,
            "description": entry.description,
            "status": entry.status,
            "filename": entry.image_relpath
            if entry.image_relpath
            else f"{entry.timestamp}.png",
            "app_name": entry.app,
            "window_title": entry.title,
        }
        for entry in entries
    ]

    return render_template("index.html", entries=serialized_entries, stats=stats)


@app.route("/timeline")
def timeline():
    """Timeline slider view - preserved from original."""
    entries = sql_store.get_timeline_data()
    return render_template("timeline.html", entries=entries)


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
                "filename": entry.image_relpath
                if entry.image_relpath
                else f"{entry.timestamp}.png",
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
        entries = search_engine.search_debug(q, limit=50)
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
