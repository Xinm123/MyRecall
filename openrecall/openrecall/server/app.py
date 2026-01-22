import os
import base64
import logging
from threading import Thread
from datetime import datetime
from pathlib import Path

import numpy as np
from flask import Flask, render_template, request, send_from_directory

from openrecall.shared.config import settings
from openrecall.server.memory_card import build_memory_card, extract_human_description
from openrecall.server.api import api_bp
from openrecall.server.database import (
    create_db,
    get_all_entries,
    get_all_entries_with_status,
    get_timestamps,
    get_entries_by_time_range,
    get_entries_since,
    get_entries_until,
    reset_stuck_tasks,
    fts_search,
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
            "description": extract_human_description(entry.description),
            "status": entry.status,
            "filename": f"{entry.timestamp}.png",
            "app_name": entry.app,
            "window_title": entry.title,
        }
        for entry in entries
    ]

    return render_template("index.html", entries=serialized_entries, stats=stats)


@app.route("/timeline")
def timeline():
    """Timeline slider view - preserved from original."""
    timestamps = get_timestamps()
    return render_template("timeline.html", timestamps=timestamps)


@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    start_time_str = (request.args.get("start_time") or "").strip()
    end_time_str = (request.args.get("end_time") or "").strip()
    if q and not start_time_str and not end_time_str:
        from openrecall.server.query_parsing import split_query

        parsed = split_query(q, now=datetime.now())
        if parsed.start_ts is not None or parsed.end_ts is not None:
            start_time_str = ""
            end_time_str = ""
        q = parsed.q_semantic

    def parse_minute_start(value: str) -> int | None:
        if not value:
            return None
        try:
            return int(datetime.strptime(value, "%Y-%m-%dT%H:%M").timestamp())
        except ValueError:
            return None

    start_min = parse_minute_start(start_time_str)
    end_min = parse_minute_start(end_time_str)

    if q:
        from openrecall.server.query_parsing import parse_time_range

        inferred_start, inferred_end, cleaned = parse_time_range(q, now=datetime.now())
        if start_min is None and end_min is None and (inferred_start is not None or inferred_end is not None):
            start_min = inferred_start
            end_min = inferred_end
            q = cleaned

    if start_min is not None and end_min is not None:
        if start_min > end_min:
            start_min, end_min = end_min, start_min
        entries = get_entries_by_time_range(start_min, end_min + 59)
    elif start_min is not None:
        entries = get_entries_since(start_min)
    elif end_min is not None:
        entries = get_entries_until(end_min + 59)
    else:
        entries = get_all_entries()

    hard_limit = int(getattr(settings, "hard_limit_recent_n", 0) or 0)
    if hard_limit > 0 and len(entries) > hard_limit:
        entries = entries[:hard_limit]

    if not q:
        return render_template("search.html", entries=entries, reasons={})

    id_to_entry = {e.id: e for e in entries if e.id is not None}
    candidate_ids = list(id_to_entry.keys())

    vec_ranked_ids: list[int] = []
    vec_score_map: dict[int, float] = {}
    try:
        from openrecall.server.ai.factory import get_mm_embedding_provider
        from openrecall.server.vector_backend import CacheVectorBackend, get_vector_backend

        mm = get_mm_embedding_provider()
        query_vec = mm.embed_text(q)
        backend = get_vector_backend()
        if backend.__class__.__name__ == "CacheVectorBackend":
            b: CacheVectorBackend = backend
            items = []
            for entry in entries:
                if entry.id is None:
                    continue
                vec = entry.image_embedding
                if vec is None:
                    vec = np.zeros(int(settings.embedding_dim), dtype=np.float32)
                items.append((entry.id, vec))
            b.bulk_upsert(items)
            hits = b.query(query_vec, topk=50, candidate_ids=candidate_ids)
        else:
            hits = backend.query(query_vec, topk=50, candidate_ids=candidate_ids)
            close_fn = getattr(backend, "close", None)
            if callable(close_fn):
                close_fn()
        vec_ranked_ids = [hid for hid, _ in hits]
        vec_score_map = {hid: float(score) for hid, score in hits}
    except Exception:
        vec_ranked_ids = []
        vec_score_map = {}

    fts_ranked_ids: list[int] = []
    try:
        import sqlite3

        with sqlite3.connect(str(settings.db_path)) as conn:
            hits = fts_search(conn, q, topk=50)
        cand = set(candidate_ids)
        fts_ranked_ids = [hid for hid, _ in hits if hid in cand]
    except Exception:
        fts_ranked_ids = []

    from openrecall.server.fusion import rrf_fuse

    fused = rrf_fuse([vec_ranked_ids, fts_ranked_ids], k=60)
    fused_ids = [doc_id for doc_id, _ in fused]
    if not fused_ids:
        embeddings = [entry.embedding for entry in entries]
        query_embedding = get_embedding(q)
        similarities = [cosine_similarity(query_embedding, emb) for emb in embeddings]
        indices = np.argsort(similarities)[::-1]
        sorted_entries = [entries[i] for i in indices]
        sorted_similarities = [similarities[i] for i in indices]
        for entry, similarity in zip(sorted_entries, sorted_similarities):
            entry.similarity_score = similarity
        return render_template("search.html", entries=sorted_entries, reasons={})

    sorted_entries = [id_to_entry[i] for i in fused_ids if i in id_to_entry]
    rerank_score_map: dict[int, float] = {}
    if bool(getattr(settings, "rerank_enabled", False)):
        try:
            from openrecall.server.ai.factory import get_reranker_provider

            reranker = get_reranker_provider()
            topn = int(getattr(settings, "rerank_topk", 50) or 50)
            if topn < 1:
                topn = 1
            topn = min(topn, len(sorted_entries))
            include_image = bool(getattr(settings, "rerank_include_image", False))
            image_topk = int(getattr(settings, "rerank_image_topk", 10) or 10)
            use_image = include_image and topn <= max(1, image_topk)
            batch = []
            for e in sorted_entries[:topn]:
                if e.id is None:
                    continue
                card = build_memory_card(
                    app=e.app,
                    title=e.title,
                    timestamp=e.timestamp,
                    ocr_text=e.text,
                    vision_description=e.description,
                )
                item = {
                    "id": e.id,
                    "timestamp": e.timestamp,
                    "time_bucket": card.time_bucket,
                    "app": e.app,
                    "title": e.title,
                    "scene": card.scene,
                    "actions": card.actions,
                    "entities": card.entities,
                    "keywords": card.keywords,
                    "ui_text": card.ui_text,
                    "text": e.text,
                    "description": e.description,
                    "description_text": extract_human_description(e.description),
                }
                if use_image:
                    try:
                        img_path = settings.screenshots_path / f"{int(e.timestamp)}.png"
                        if img_path.is_file():
                            item["image_url"] = "data:image/png;base64," + base64.b64encode(
                                img_path.read_bytes()
                            ).decode("ascii")
                    except Exception:
                        pass
                batch.append(item)
            reranked = reranker.rerank(q, batch)
            reranked_ids = [int(x["id"]) for x in reranked if isinstance(x, dict) and "id" in x]
            rerank_score_map = {
                int(x["id"]): float(x.get("rerank_score") or 0.0)
                for x in reranked
                if isinstance(x, dict) and "id" in x
            }
            if reranked_ids:
                seen = set(reranked_ids)
                remaining = [e for e in sorted_entries if (e.id is not None and int(e.id) not in seen)]
                sorted_entries = [id_to_entry[i] for i in reranked_ids if i in id_to_entry] + remaining
        except Exception:
            rerank_score_map = {}
    for entry in sorted_entries:
        if entry.id is not None and int(entry.id) in rerank_score_map:
            entry.similarity_score = float(rerank_score_map[int(entry.id)])
            continue
        score = vec_score_map.get(entry.id or -1)
        if score is None:
            entry.similarity_score = None
        elif -1.0 <= score <= 1.0:
            entry.similarity_score = (score + 1.0) / 2.0
        else:
            entry.similarity_score = None
    reasons = {}
    try:
        import re
        from markupsafe import Markup, escape

        vec_set = set(vec_ranked_ids)
        fts_set = set(fts_ranked_ids)
        terms = [t for t in re.split(r"\s+", q) if t and len(t) >= 2][:5]

        def build_snippet(text: str | None) -> Markup | None:
            raw = (text or "").strip()
            if not raw:
                return None
            window = raw[:220]
            for term in terms:
                idx = raw.find(term)
                if idx != -1:
                    start = max(0, idx - 60)
                    end = min(len(raw), idx + 160)
                    window = raw[start:end]
                    break
            escaped = str(escape(window))
            for term in terms:
                escaped = escaped.replace(str(escape(term)), f"<mark>{escape(term)}</mark>")
            return Markup(escaped)

        for e in sorted_entries:
            if e.id is None:
                continue
            tags = []
            if int(e.id) in fts_set:
                tags.append("关键词")
            if int(e.id) in vec_set:
                tags.append("语义")
            desc = extract_human_description(e.description)
            snippet = build_snippet((e.text or "") + ("\n" + desc if desc else ""))
            reasons[int(e.id)] = {
                "tags": tags,
                "snippet": snippet,
                "rerank_score": rerank_score_map.get(int(e.id)),
            }
    except Exception:
        reasons = {}
    return render_template("search.html", entries=sorted_entries, reasons=reasons)


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
