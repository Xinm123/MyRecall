import os
import logging
from threading import Thread
from datetime import datetime

import numpy as np
from flask import Flask, render_template, request, send_from_directory

from openrecall.shared.config import settings
from openrecall.server.api import api_bp
from openrecall.server.database import (
    create_db,
    get_all_entries,
    get_all_entries_with_status,
    get_timestamps,
    get_entries_by_time_range,
    reset_stuck_tasks,
)
from openrecall.server.nlp import cosine_similarity, get_embedding
from openrecall.shared.utils import human_readable_time, timestamp_to_human_readable

logger = logging.getLogger(__name__)

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
    entries = get_all_entries_with_status()
    # Sort by timestamp descending (newest first)
    entries.sort(key=lambda x: x.timestamp, reverse=True)
    return render_template("index.html", entries=entries)


@app.route("/timeline")
def timeline():
    """Timeline slider view - preserved from original."""
    timestamps = get_timestamps()
    return render_template("timeline.html", timestamps=timestamps)


@app.route("/search")
def search():
    q = request.args.get("q")
    start_time_str = request.args.get("start_time")
    end_time_str = request.args.get("end_time")

    if start_time_str and end_time_str:
        start_time = int(
            datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M").timestamp()
        )
        end_time = int(datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M").timestamp())
        entries = get_entries_by_time_range(start_time, end_time)
    else:
        entries = get_all_entries()

    embeddings = [entry.embedding for entry in entries]
    query_embedding = get_embedding(q)
    similarities = [cosine_similarity(query_embedding, emb) for emb in embeddings]
    indices = np.argsort(similarities)[::-1]
    sorted_entries = [entries[i] for i in indices]
    sorted_similarities = [similarities[i] for i in indices]
    
    # Add similarity score to each entry
    for entry, similarity in zip(sorted_entries, sorted_similarities):
        entry.similarity_score = similarity

    return render_template("search.html", entries=sorted_entries)


@app.route("/static/<filename>")
def serve_image(filename):
    return send_from_directory(str(settings.screenshots_path), filename)


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    """Serve screenshot images from the screenshots directory."""
    return send_from_directory(str(settings.screenshots_path), filename)


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
    count = reset_stuck_tasks()
    if count > 0:
        logger.warning(f"⚠️ Recovered {count} stuck tasks (Zombies) from previous session.")
    
    # Step 2: Start the Engine
    worker = ProcessingWorker()
    worker.daemon = True  # Ensure it dies when main process dies
    worker.start()
    
    # Step 3: Attach to App (Crucial: Prevents Garbage Collection)
    app_instance.worker = worker
    logger.info("🚀 Background Processing Worker started successfully.")
